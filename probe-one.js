// probe-one.js — отдельный скрипт-логгер для Google One.
// Цель: только ловить, что Google One сам спрашивает у Play Billing,
// и что Play отвечает. Ничего не покупает, launchBillingFlow здесь нет.
//
// Зачем: живые sku/offer для Ultra/Pro видны только в ответе
// BillingClient, а не на экране Upgrade и не в HTML one.google.com.
// Этот скрипт пишет в лог каждый productId, offerId, basePlanId,
// цену и период первого pricing phase, и offerToken (только первые
// 12 символов, полный токен в лог не пишется).
//
// Как запускать (на компьютере, эмулятор уже запущен, root есть):
//   frida-server должен быть запущен от root, см. артефакт
//   "Frida Google One — от начала до конца", раздел про su.
//   1) Запустить Google One на эмуляторе.
//   2) Узнать pid: adb -s emulator-5554 shell pidof com.google.android.apps.subscriptions.red
//   3) Прицепиться:
//      frida -U -p <pid> -l probe-one.js --no-pause
//      или с запуском приложения:
//      frida -U -f com.google.android.apps.subscriptions.red -l probe-one.js --no-pause
//   4) Нажать Upgrade в Google One и смотреть лог: строки [probe].
//      Сначала скрипт сам опрашивает CANDIDATES, потом ловит
//      запросы самого приложения.
//
// Выход: строки вида
//   [probe] offer product=g1.play.20tb offerId=eft-12month basePlan=monthly price=0 period=P1Y
//   [probe] app_query product=g1.ai.pro
// Если для sku ничего не вернулось — Play его для этого аккаунта
// не знает, это нормально, такой sku просто пропускается.

var DEX_PATHS = [
  "/data/local/tmp/module_521.apk",
  "/data/local/tmp/billing.apk"
];

// Кандидаты для опроса. Несуществующие Play сам игнорирует,
// возвращаются только живые. Сюда же добавляются новые sku,
// когда они находятся в логе app_query.
var CANDIDATES = [
  "g1.play.20tb",
  "g1.play.ai.pro",
  "g1.ai.pro",
  "g1.30tb",
  "g1.20tb.v2",
  "g1.2tb.ai.subs_variant",
  "g1.play.2tb.ai",
  "g1.2tb.ai",
  "g1.2tb.subs_variant",
  "g1.2tb.6months_eft",
  "g1.play.helium",
  "g1.helium",
  "g1.2tb",
  "g1.100gb",
  "g1.200gb",
  "g1.10tb.1month_ip_90p",
  "g1.10tb.3months_ip_85p",
  "g1.20tb.3months_ip_90p.acq",
  "g1.ai.ultra.1month_ip_90p.acq",
  "g1.ai.ultra.3months_ip_90p.acq"
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
  // BillingClient может быть уже в загрузчике приложения.
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

// Хук на то, что Google One сам спрашивает у Play.
// Ловит productId в JSONObject.put / Bundle.putString, когда
// приложение нажимает Upgrade. Это самый простой способ увидеть
// живой sku, который использует сам интерфейс.
function hookAppQueries() {
  try {
    var JSONObject = Java.use("org.json.JSONObject");
    JSONObject.put.overload("java.lang.String", "java.lang.Object").implementation = function (k, v) {
      try {
        var key = String(k);
        if (key === "productId" || key === "skuId" || key === "product_id" || key === "sku") {
          log("app_query", { product: String(v) });
        }
      } catch (e) {}
      return this.put(k, v);
    };
  } catch (e) { log("hook_json_err", { m: clip(e) }); }
  try {
    var Bundle = Java.use("android.os.Bundle");
    Bundle.putString.overload("java.lang.String", "java.lang.String").implementation = function (k, v) {
      try {
        var key = String(k);
        if (key === "productId" || key === "skuId" || key === "product_id") {
          log("app_query", { product: String(v) });
        }
      } catch (e) {}
      return this.putString(k, v);
    };
  } catch (e) { log("hook_bundle_err", { m: clip(e) }); }
}

function logOffers(list) {
  L(dexLoader);
  var PD = Java.use("com.android.billingclient.api.ProductDetails");
  var SOD = Java.use("com.android.billingclient.api.ProductDetails$SubscriptionOfferDetails");
  var PP = Java.use("com.android.billingclient.api.ProductDetails$PricingPhase");
  for (var i = 0; i < list.size(); i++) {
    var pd = Java.cast(list.get(i), PD);
    var pid = String(pd.getProductId());
    log("product", { id: pid, title: String(pd.getTitle() || "") });
    var offs = pd.getSubscriptionOfferDetails();
    if (!offs) { log("no_offers", { product: pid }); continue; }
    for (var j = 0; j < offs.size(); j++) {
      var o = Java.cast(offs.get(j), SOD);
      var oid = String(o.getOfferId() || "");
      var base = String(o.getBasePlanId() || "");
      var tok = String(o.getOfferToken() || "");
      var price = "", period = "", mode = "";
      try {
        var ph = o.getPricingPhases().getPricingPhaseList();
        if (ph && ph.size() > 0) {
          var first = Java.cast(ph.get(0), PP);
          price = String(first.getPriceAmountMicros());
          period = String(first.getBillingPeriod());
          mode = String(first.getRecurrenceMode());
        }
      } catch (e2) {}
      log("offer", {
        product: pid, offerId: oid, basePlan: base,
        priceMicros: price, period: period, recurrenceMode: mode,
        token: tok ? tok.slice(0, 12) + "..." : ""
      });
    }
  }
}

function queryCandidates() {
  L(dexLoader);
  var Prod = Java.use("com.android.billingclient.api.QueryProductDetailsParams$Product");
  var Params = Java.use("com.android.billingclient.api.QueryProductDetailsParams");
  var PDL = Java.use("com.android.billingclient.api.ProductDetailsResponseListener");
  var PL = Java.registerClass({
    name: "rc.PPL" + Date.now(),
    implements: [PDL],
    methods: {
      onProductDetailsResponse: function (res, list) {
        log("pd", { code: res.getResponseCode(), n: list ? list.size() : 0, msg: String(res.getDebugMessage() || "") });
        if (res.getResponseCode() !== 0 || !list) { log("done", {}); return; }
        try { logOffers(list); } catch (e) { log("log_err", { m: clip(e) }); }
        log("done", {});
      }
    }
  });
  var arr = Java.use("java.util.ArrayList").$new();
  for (var i = 0; i < CANDIDATES.length; i++) {
    arr.add(Prod.newBuilder().setProductId(CANDIDATES[i]).setProductType("subs").build());
  }
  hold(PL);
  clientRef.queryProductDetailsAsync(Params.newBuilder().setProductList(arr).build(), hold(PL.$new()));
  log("query_sent", { n: arr.size(), skus: CANDIDATES.join(",") });
}

function boot() {
  if (!loadBilling()) return;
  hookAppQueries();
  var BillingClient = Java.use("com.android.billingclient.api.BillingClient");
  var PUL = Java.use("com.android.billingclient.api.PurchasesUpdatedListener");
  var Lst = Java.registerClass({
    name: "rc.PPA" + Date.now(),
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
    name: "rc.PPB" + Date.now(),
    implements: [SLL],
    methods: {
      onBillingSetupFinished: function (r) {
        log("setup", { code: r.getResponseCode(), msg: String(r.getDebugMessage() || "") });
        if (r.getResponseCode() === 0) queryCandidates();
      },
      onBillingServiceDisconnected: function () { log("disc", {}); }
    }
  });
  hold(SL);
  clientRef.startConnection(hold(SL.$new()));
}

rpc.exports = {
  probe: function () {
    Java.perform(function () { queryCandidates(); });
    return "probe sent";
  },
  status: function () {
    return { booted: !!clientRef, candidates: CANDIDATES.length };
  }
};

var scriptStarted = false;
setImmediate(function () {
  Java.perform(function () {
    if (scriptStarted) return;
    scriptStarted = true;
    log("script_start", { candidates: CANDIDATES.length });
    boot();
  });
});
