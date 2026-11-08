package org.asta.mobile;

import android.os.Bundle;
import android.webkit.JavascriptInterface;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import com.getcapacitor.BridgeActivity;

/**
 * Janela do ASTA no Android (v0.14): liga o ASTA DENTRO do aparelho (Python via Chaquopy) e deixa a página inicial (www/index.html) abri-lo.
 * O app não precisa mais do ASTA de um computador; conectar a um computador continua sendo uma opção na própria página inicial.
 */
public class MainActivity extends BridgeActivity {
    private volatile String localUrl = "";
    private volatile String error = "";

    /** Ponte para a página inicial: ela pergunta se o ASTA do aparelho já está pronto. */
    public class Engine {
        @JavascriptInterface
        public String getLocalUrl() {
            return localUrl;
        }

        @JavascriptInterface
        public String getError() {
            return error;
        }
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getBridge().getWebView().addJavascriptInterface(new Engine(), "AstaEngine");
        final String filesDir = getFilesDir().getAbsolutePath();
        final String nativeDir = getApplicationInfo().nativeLibraryDir;
        final android.content.Context ctx = getApplicationContext();
        new Thread(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(ctx));
                }
                localUrl = Python.getInstance().getModule("asta_android").callAttr("start", filesDir, nativeDir).toString();
            } catch (Throwable t) {
                error = String.valueOf(t);
            }
        }, "asta-engine").start();
    }
}
