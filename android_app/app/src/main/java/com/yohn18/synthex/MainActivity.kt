package com.yohn18.synthex

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.*
import android.widget.*
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var webView: WebView
    private lateinit var connectLayout: LinearLayout
    private lateinit var ipInput: EditText
    private lateinit var portInput: EditText
    private lateinit var statusText: TextView

    companion object {
        const val PREF_IP   = "last_ip"
        const val PREF_PORT = "last_port"
        const val DEF_PORT  = "8765"
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences("synthex", Context.MODE_PRIVATE)

        // Fullscreen dark
        window.statusBarColor    = Color.parseColor("#0a0a0f")
        window.navigationBarColor = Color.parseColor("#0a0a0f")
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0a0a0f"))
        }
        setContentView(root)

        // ── WebView (hidden until connected) ─────────────────────────────────
        webView = WebView(this).apply {
            visibility = View.GONE
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.MATCH_PARENT)
            settings.apply {
                javaScriptEnabled      = true
                domStorageEnabled      = true
                allowFileAccess        = false
                allowContentAccess     = false
                setSupportZoom(false)
                displayZoomControls    = false
                builtInZoomControls    = false
                useWideViewPort        = true
                loadWithOverviewMode   = true
                mixedContentMode       = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            }
            webChromeClient = WebChromeClient()
            webViewClient   = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    connectLayout.visibility = View.GONE
                    webView.visibility       = View.VISIBLE
                }
                override fun onReceivedError(
                    view: WebView?, req: WebResourceRequest?,
                    err: WebResourceError?) {
                    if (req?.isForMainFrame == true) {
                        showConnect("Tidak bisa terhubung ke PC — cek IP & pastikan Synthex PC berjalan")
                    }
                }
            }
        }
        root.addWidget(webView)

        // ── Connect screen ────────────────────────────────────────────────────
        connectLayout = buildConnectLayout(root)
        root.addWidget(connectLayout)

        // Auto-connect jika sudah ada IP tersimpan
        val savedIp = prefs.getString(PREF_IP, "")
        if (!savedIp.isNullOrBlank()) {
            ipInput.setText(savedIp)
            portInput.setText(prefs.getString(PREF_PORT, DEF_PORT))
            doConnect()
        }
    }

    private fun LinearLayout.addWidget(v: View) = addView(v)

    private fun buildConnectLayout(root: LinearLayout): LinearLayout {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(40), dp(24), dp(24))
            setBackgroundColor(Color.parseColor("#0a0a0f"))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.MATCH_PARENT)
        }

        // Logo + title
        val logoRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity     = android.view.Gravity.CENTER_VERTICAL
        }
        val logoBg = TextView(this).apply {
            text    = "SX"
            setTextColor(Color.WHITE)
            textSize = 18f
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            gravity  = android.view.Gravity.CENTER
            setBackgroundColor(Color.parseColor("#6c4aff"))
            setPadding(dp(14), dp(10), dp(14), dp(10))
        }
        val titleLbl = TextView(this).apply {
            text     = "  Synthex"
            setTextColor(Color.parseColor("#e2e8f0"))
            textSize  = 22f
            typeface  = android.graphics.Typeface.DEFAULT_BOLD
        }
        logoRow.addView(logoBg)
        logoRow.addView(titleLbl)
        layout.addView(logoRow)

        layout.addView(spacer(dp(32)))

        layout.addView(label("IP Address PC Synthex", "#64748b", 12f))
        layout.addView(spacer(dp(6)))

        ipInput = editText("192.168.x.x", android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS)
        layout.addView(ipInput)
        layout.addView(spacer(dp(10)))

        layout.addView(label("Port (default 8765)", "#64748b", 12f))
        layout.addView(spacer(dp(6)))

        portInput = editText(DEF_PORT, android.text.InputType.TYPE_CLASS_NUMBER)
        layout.addView(portInput)
        layout.addView(spacer(dp(20)))

        val connectBtn = Button(this).apply {
            text     = "Hubungkan ke PC"
            setTextColor(Color.WHITE)
            textSize  = 15f
            typeface  = android.graphics.Typeface.DEFAULT_BOLD
            setBackgroundColor(Color.parseColor("#6c4aff"))
            setPadding(0, dp(14), 0, dp(14))
            setOnClickListener { doConnect() }
        }
        layout.addView(connectBtn)
        layout.addView(spacer(dp(14)))

        statusText = label("Masukkan IP PC kamu lalu tap Hubungkan", "#64748b", 12f)
        statusText.gravity = android.view.Gravity.CENTER_HORIZONTAL
        layout.addView(statusText)

        layout.addView(spacer(dp(32)))

        // Info box
        val infoBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(14))
            setBackgroundColor(Color.parseColor("#111118"))
        }
        infoBox.addView(label("Cara menggunakan:", "#9d5cf6", 13f, bold = true))
        infoBox.addView(spacer(dp(8)))
        for (txt in listOf(
            "1. Buka Synthex di PC",
            "2. Buka halaman Remote",
            "3. Klik ▶ Jalankan Server Companion",
            "4. Masukkan IP PC di kolom atas",
            "5. Tap Hubungkan"
        )) {
            infoBox.addView(label(txt, "#64748b", 12f))
            infoBox.addView(spacer(dp(3)))
        }
        layout.addView(infoBox)

        return layout
    }

    private fun doConnect() {
        val ip   = ipInput.text.toString().trim()
        val port = portInput.text.toString().trim().ifBlank { DEF_PORT }
        if (ip.isBlank()) {
            statusText.text = "Masukkan IP PC dulu"
            statusText.setTextColor(Color.parseColor("#f87171"))
            return
        }
        val url = "http://$ip:$port"
        statusText.text = "Menghubungkan ke $url..."
        statusText.setTextColor(Color.parseColor("#f59e0b"))

        prefs.edit().putString(PREF_IP, ip).putString(PREF_PORT, port).apply()

        webView.loadUrl(url)
        connectLayout.visibility = View.VISIBLE
    }

    private fun showConnect(msg: String) {
        webView.visibility       = View.GONE
        connectLayout.visibility = View.VISIBLE
        statusText.text = msg
        statusText.setTextColor(Color.parseColor("#f87171"))
    }

    override fun onBackPressed() {
        if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
            webView.goBack()
        } else if (webView.visibility == View.VISIBLE) {
            showConnect("Kembali ke layar koneksi")
        } else {
            super.onBackPressed()
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private fun dp(v: Int): Int =
        (v * resources.displayMetrics.density).toInt()

    private fun spacer(h: Int) = View(this).apply {
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, h)
    }

    private fun label(
        text: String, color: String, size: Float, bold: Boolean = false
    ) = TextView(this).apply {
        this.text = text
        setTextColor(Color.parseColor(color))
        textSize = size
        if (bold) typeface = android.graphics.Typeface.DEFAULT_BOLD
    }

    private fun editText(hint: String, inputType: Int) = EditText(this).apply {
        this.hint          = hint
        this.inputType     = inputType
        setHintTextColor(Color.parseColor("#374151"))
        setTextColor(Color.parseColor("#e2e8f0"))
        setBackgroundColor(Color.parseColor("#16162a"))
        textSize           = 16f
        setPadding(dp(14), dp(12), dp(14), dp(12))
    }
}
