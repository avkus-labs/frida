// probe-single.js — проверка ОДНОГО оффера из списка, только чтение.
// Шаблон: scan-offers.sh подставляет сюда TARGET_SKU и TARGET_OFFER
// (sed по __SKU__ / __OFFER__) и запускает frida на один оффер.
//
// Что делает: queryProductDetailsAsync для одного sku и смотрит,
// есть ли в ответе Play именно этот offerId. launchBillingFlow
// здесь НЕТ — ничего не открывается и не покупается, триал не
// тратится. Это и есть весь смысл: анализ, а не оформление.
//
// Выход в лог (строки [probe]):
//   [probe] offer product=... offerId=... basePlan=... priceMicros=... period=...
//   [probe] RESULT sku=... offer=... status=live|missing|error price=... period=...
//     live    — Play вернул этот offerId для этого аккаунта
//     missing — sku живой, но такого offerId в ответе нет
//     error   — BillingClient вернул код != 0 или sku вообще не найден
//   [probe] done
//
// Если offer пустой (""), это базовый план: у него offerId равен
// null, в скрипте он превращается в пустую строку.

var TARGET_SKU = "__SKU__";
var TARGET_OFFER = "__OFFER__";

var DEX_PATHS = [
  "/data/local/tmp/module_521.apk",
  "/data/local/tmp/billing.apk"
];

var dexLoader = null;
var ctxRef = null;
var clientRef = null;
var held = [];
function hold(x) { held.push(x); return x; }
function L(v) { Java.classFactory.loader = v; }
function clip(x) { try { var s = String(x); return s.length > 800 ? s.slice(0, 800) : s; } catch (e) { return "?"; } }

function log(ev, extra) {
  var o = extra || {};
  o.ev = ev;
  send(o);
  var bits = [ev];
  for (var k in extra) {
    if (k === "ev") continue;
    var v = extra[k];
    if (v === undefined || v === null || v === "") continue;
    bits.push(k + "=" + v);
  }
  console.log("[probe] " + bits.join("  "));
}

function loadBilling() {
  L(null);
  ctxRef = Java.use("android.app.ActivityThread").currentApplication().getApplicationContext();
  var DexClassLoader = Java.use("dalvik.system.DexClassLoader");
  var cache = ctxRef.getCodeCacheDir().getAbsolutePath();
  var File = Java.use("java.io.File");
  for (var i = 0; i < DEX_PATHS.length; i++) {
    try {
      if (!File.$new(DEX_PATHS[i]).exists()) continue;
      dexLoader = DexClassLoader.$new(DEX_PATHS[i], cache, null, ctxRef.getClassLoader());
      L(dexLoader);
      Java.use("com.android.billingclient.api.BillingClient");
      log("dex", { path: DEX_PATHS[i] });
      return true;
    } catch (e) {
      dexLoader = null;
      L(null);
    }
  }
  var found = null;
  Java.enumerateClassLoaders({
    onMatch: function (loader) {
      if (found) return;
      try {
        if (loader.loadClass("com.android.billingclient.api.BillingClient")) found = loader;
      } catch (e) {}
    },
    onComplete: function () {}
  });
  if (found) {
    dexLoader = found;
    L(dexLoader);
    log("dex", { path: "app-loader" });
    return true;
  }
  log("boot_err", { m: "BillingClient not found. adb push module_521.apk /data/local/tmp/" });
  return false;
}

function queryOne() {
  L(dexLoader);
  var Prod = Java.use("com.android.billingclient.api.QueryProductDetailsParams$Product");
  var Params = Java.use("com.android.billingclient.api.QueryProductDetailsParams");
  var PDL = Java.use("com.android.billingclient.api.ProductDetailsResponseListener");
  var PD = Java.use("com.android.billingclient.api.ProductDetails");
  var SOD = Java.use("com.android.billingclient.api.ProductDetails$SubscriptionOfferDetails");
  var PP = Java.use("com.android.billingclient.api.ProductDetails$PricingPhase");
  var PL = Java.registerClass({
    name: "rc.PSQ" + Date.now(),
    implements: [PDL],
    methods: {
      onProductDetailsResponse: function (res, list) {
        var code = res.getResponseCode();
        if (code !== 0 || !list || list.size() === 0) {
          log("RESULT", { sku: TARGET_SKU, offer: TARGET_OFFER, status: "error", code: code });
          log("done", {});
          return;
        }
        var found = false;
        var foundPrice = "", foundPeriod = "";
        for (var i = 0; i < list.size(); i++) {
          var pd = Java.cast(list.get(i), PD);
          var pid = String(pd.getProductId());
          var offs = pd.getSubscriptionOfferDetails();
          if (!offs) continue;
          for (var j = 0; j < offs.size(); j++) {
            var o = Java.cast(offs.get(j), SOD);
            var oid = String(o.getOfferId() || "");
            var base = String(o.getBasePlanId() || "");
            var price = "", period = "";
            try {
              var ph = o.getPricingPhases().getPricingPhaseList();
              if (ph && ph.size() > 0) {
                var first = Java.cast(ph.get(0), PP);
                price = String(first.getPriceAmountMicros());
                period = String(first.getBillingPeriod());
              }
            } catch (e2) {}
            log("offer", { product: pid, offerId: oid, basePlan: base, priceMicros: price, period: period });
            if (oid === TARGET_OFFER) {
              found = true;
              foundPrice = price;
              foundPeriod = period;
            }
          }
        }
        log("RESULT", {
          sku: TARGET_SKU, offer: TARGET_OFFER,
          status: found ? "live" : "missing",
          priceMicros: foundPrice, period: foundPeriod
        });
        log("done", {});
      }
    }
  });
  var arr = Java.use("java.util.ArrayList").$new();
  arr.add(Prod.newBuilder().setProductId(TARGET_SKU).setProductType("subs").build());
  hold(PL);
  clientRef.queryProductDetailsAsync(Params.newBuilder().setProductList(arr).build(), hold(PL.$new()));
  log("query_sent", { sku: TARGET_SKU, offer: TARGET_OFFER });
}

function boot() {
  if (!loadBilling()) { log("done", {}); return; }
  var BillingClient = Java.use("com.android.billingclient.api.BillingClient");
  var PUL = Java.use("com.android.billingclient.api.PurchasesUpdatedListener");
  var Lst = Java.registerClass({
    name: "rc.PSA" + Date.now(),
    implements: [PUL],
    methods: {
      onPurchasesUpdated: function (r, p) {
        log("purchase_cb", { code: r.getResponseCode(), n: p ? p.size() : 0 });
      }
    }
  });
  var b = BillingClient.newBuilder(ctxRef);
  b.setListener(hold(Lst.$new()));
  hold(Lst);
  try { b.enablePendingPurchases(); } catch (e) {}
  clientRef = b.build();
  var SLL = Java.use("com.android.billingclient.api.BillingClientStateListener");
  var SL = Java.registerClass({
    name: "rc.PSB" + Date.now(),
    implements: [SLL],
    methods: {
      onBillingSetupFinished: function (r) {
        log("setup", { code: r.getResponseCode(), msg: String(r.getDebugMessage() || "") });
        if (r.getResponseCode() === 0) queryOne();
        else {
          log("RESULT", { sku: TARGET_SKU, offer: TARGET_OFFER, status: "error", code: r.getResponseCode() });
          log("done", {});
        }
      },
      onBillingServiceDisconnected: function () { log("disc", {}); }
    }
  });
  hold(SL);
  clientRef.startConnection(hold(SL.$new()));
}

var scriptStarted = false;
setImmediate(function () {
  Java.perform(function () {
    if (scriptStarted) return;
    scriptStarted = true;
    log("script_start", { sku: TARGET_SKU, offer: TARGET_OFFER });
    boot();
  });
});
