package ir.hazan.weather;

import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;

public class SafeWebViewClient extends WebViewClient {
    @Override
    public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
        view.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        view.loadUrl(request.getUrl().toString());
        return true;
    }
}
