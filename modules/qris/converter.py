# -*- coding: utf-8 -*-
"""
modules/qris/converter.py
Konversi QRIS statis → QRIS dinamis dengan jumlah dan biaya layanan.

Algoritma berdasarkan standar QRIS (EMVCo CPAS) Indonesia:
  - TLV encoding: Tag(2) + Length(2) + Value(n)
  - CRC16-CCITT (poly 0x1021, init 0xFFFF)
  - Tag 01: "11"=statis, "12"=dinamis
  - Tag 54: jumlah transaksi (hanya di QR dinamis)
  - Tag 55/56/57: biaya layanan (opsional)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import io


class QRISError(Exception):
    pass


@dataclass
class TLV:
    tag: str
    value: str
    children: list["TLV"] = field(default_factory=list)

    def encode(self) -> str:
        body = "".join(c.encode() for c in self.children) if self.children else self.value
        length = len(body)
        if length > 99:
            raise QRISError(f"TLV tag {self.tag} terlalu panjang ({length} char, maks 99).")
        return self.tag + str(length).zfill(2) + body


# ── TLV field names (informatif) ─────────────────────────────────────────────
_TAG_NAMES = {
    "00": "Payload Format Indicator",
    "01": "Point of Initiation Method",
    "52": "Merchant Category Code",
    "53": "Transaction Currency",
    "54": "Transaction Amount",
    "55": "Tip or Convenience Indicator",
    "56": "Value of Convenience Fee Fixed",
    "57": "Value of Convenience Fee Percentage",
    "58": "Country Code",
    "59": "Merchant Name",
    "60": "Merchant City",
    "61": "Postal Code",
    "62": "Additional Data Field",
    "63": "CRC",
}


def _parse_tlv(data: str, nested_tags: set[str] | None = None) -> list[TLV]:
    """Parse flat TLV string into list of TLV objects. Recurse for nested tags."""
    if nested_tags is None:
        nested_tags = {str(i).zfill(2) for i in range(26, 52)} | {"62"}

    result: list[TLV] = []
    i = 0
    while i < len(data):
        if i + 4 > len(data):
            break
        tag = data[i:i+2]
        try:
            length = int(data[i+2:i+4])
        except ValueError:
            break
        i += 4
        value = data[i:i+length]
        i += length

        if tag in nested_tags:
            children = _parse_tlv(value)
            result.append(TLV(tag=tag, value=value, children=children))
        else:
            result.append(TLV(tag=tag, value=value))

    return result


def _crc16(data: str) -> str:
    """CRC16-CCITT (poly=0x1021, init=0xFFFF) — kembalikan hex 4 char uppercase."""
    crc = 0xFFFF
    for ch in data:
        crc ^= ord(ch) << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return format(crc, "04X")


class QRISConverter:
    """Konverter QRIS statis ke dinamis."""

    # Tag yang dikelola sendiri saat konversi
    _MANAGED = {"54", "55", "56", "57", "63"}

    def validate(self, qris: str) -> tuple[bool, str]:
        """Validasi format QRIS. Kembalikan (valid, pesan_error)."""
        qris = qris.strip()
        if not qris.startswith("000201"):
            return False, "QRIS harus diawali '000201'."
        if len(qris) < 10:
            return False, "QRIS terlalu pendek."
        # Cek CRC — body adalah semua data sebelum field CRC (strip 8 char: "6304XXXX")
        body  = qris[:-8]
        tag63 = qris[-8:-4]
        crc   = qris[-4:]
        if tag63 != "6304":
            return False, "Field CRC (6304) tidak ditemukan di akhir string."
        expected = _crc16(body + "6304")
        if crc.upper() != expected:
            return False, f"CRC tidak valid. Diharapkan {expected}, dapat {crc.upper()}."
        # Cek tag 01 ada
        elements = _parse_tlv(qris[:-8])
        tags = {t.tag for t in elements}
        if "01" not in tags:
            return False, "Field Point of Initiation Method (01) tidak ditemukan."
        if "58" not in tags:
            return False, "Field Country Code (58) tidak ditemukan."
        return True, ""

    def to_dynamic(
        self,
        qris: str,
        amount: int,
        fee_type: Optional[str] = None,   # "fixed" | "percent"
        fee_value: float = 0,
    ) -> str:
        """
        Konversi QRIS statis ke dinamis.

        Args:
            qris       : String QRIS statis (mentah dari QR code)
            amount     : Jumlah transaksi dalam Rupiah (integer)
            fee_type   : None | "fixed" | "percent"
            fee_value  : Nilai biaya (Rupiah jika fixed, angka persen jika percent)

        Returns:
            String QRIS dinamis siap di-encode ke QR image.
        """
        qris = qris.strip()
        if amount <= 0:
            raise QRISError("Jumlah harus lebih dari 0.")

        # Buang CRC lama (8 char terakhir: "6304XXXX")
        body = qris[:-8]
        elements = _parse_tlv(body)

        result: list[TLV] = []
        amount_str = str(amount)
        amount_inserted = False

        for el in elements:
            if el.tag in self._MANAGED:
                continue

            if el.tag == "01":
                # Ubah statis (11) → dinamis (12)
                result.append(TLV(tag="01", value="12"))
                continue

            if el.tag == "58" and not amount_inserted:
                # Sisipkan amount sebelum Country Code
                result.append(TLV(tag="54", value=amount_str))

                # Biaya layanan
                if fee_type == "fixed" and fee_value > 0:
                    result.append(TLV(tag="55", value="02"))
                    result.append(TLV(tag="56", value=str(fee_value)))
                elif fee_type == "percent" and fee_value > 0:
                    result.append(TLV(tag="55", value="03"))
                    result.append(TLV(tag="57", value=str(fee_value)))

                amount_inserted = True

            result.append(el)

        if not amount_inserted:
            raise QRISError("Field Country Code (58) tidak ditemukan — tidak bisa sisipkan amount.")

        # Encode ulang TLV
        encoded = "".join(t.encode() for t in result)
        crc_input = encoded + "6304"
        crc = _crc16(crc_input)
        return crc_input + crc

    def parse_info(self, qris: str) -> dict:
        """Ekstrak info merchant dari QRIS string (nama, kota, jumlah, dll)."""
        body = qris[:-8] if len(qris) >= 8 and qris[-8:-4] == "6304" else qris.strip()
        elements = _parse_tlv(body)
        info: dict = {}
        for el in elements:
            if el.tag == "01":
                info["method"] = "dinamis" if el.value == "12" else "statis"
            elif el.tag == "54":
                info["amount"] = el.value
            elif el.tag == "58":
                info["country"] = el.value
            elif el.tag == "59":
                info["merchant_name"] = el.value
            elif el.tag == "60":
                info["merchant_city"] = el.value
            elif el.tag == "52":
                info["merchant_category"] = el.value
            elif el.tag == "53":
                info["currency"] = "IDR" if el.value == "360" else el.value
        return info


def generate_qr_image(qris_string: str, box_size: int = 6, border: int = 3):
    """
    Buat PIL Image dari string QRIS.
    Kembalikan PIL.Image object.
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(qris_string)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").get_image()
    except Exception as e:
        raise QRISError(f"Gagal generate QR image: {e}")
