var TARGET = "";
var STACK = false; // false — новая подписка, true — продление действующей (ReplacementMode=5, CHARGE_FULL_PRICE)
var ADDON = "";

var PLANS = {
  // ---- Lite 30 ГБ ----
  lite_base: { sku: "g1.30gb", offer: "", note: "Lite 30 ГБ базовый $0.89/мес." },
  lite_annual: { sku: "g1.30gb.annual", offer: "", note: "Lite 30 ГБ годовой $8.99/год." },
  lite_1m: { sku: "g1.30gb.1month_eft", offer: "eft-1month", note: "Lite 30 ГБ 1 месяц бесплатно, затем $0.89/мес." },
  lite_3m_85: { sku: "g1.30gb.3months_ip_85p.acq", offer: "introprice", note: "$0.15 Lite 30 ГБ 3 месяца, затем $0.89/мес." },
  // ---- Basic 100 ГБ ----
  basic_base: { sku: "g1.100gb", offer: "", note: "Basic 100 ГБ базовый $1.99/мес." },
  basic_annual: { sku: "g1.100gb.annual", offer: "", note: "Basic 100 ГБ годовой $19.99/год." },
  basic_1m: { sku: "g1.100gb.1month_eft", offer: "freetrial", note: "Basic 100 ГБ 1 месяц бесплатно, затем $1.99/мес." },
  basic_3m: { sku: "g1.100gb.3months_eft", offer: "freetrial", note: "Basic 100 ГБ 3 месяца бесплатно, затем $1.99/мес." },
  basic_3m_85: { sku: "g1.100gb.3months_ip_85p.acq", offer: "introprice", note: "$0.29 Basic 100 ГБ 3 месяца, затем $1.99/мес." },
  // ---- Standard 200 ГБ ----
  std_base: { sku: "g1.200gb", offer: "", note: "Standard 200 ГБ базовый $2.99/мес." },
  std_annual: { sku: "g1.200gb.annual", offer: "", note: "Standard 200 ГБ годовой $29.99/год." },
  std_1m: { sku: "g1.200gb.1month_eft", offer: "freetrial", note: "Standard 200 ГБ 1 месяц бесплатно, затем $2.99/мес." },
  std_3m: { sku: "g1.200gb.3months_eft", offer: "freetrial", note: "Standard 200 ГБ 3 месяца бесплатно, затем $2.99/мес." },
  std_3m_85: { sku: "g1.200gb.3months_ip_85p.acq", offer: "introprice", note: "$0.49 Standard 200 ГБ 3 месяца, затем $2.99/мес." },
  // ---- Plus 400 ГБ (helium) ----
  helium_base: { sku: "g1.helium", offer: "", note: "Plus 400 ГБ базовый $4.99/мес. [кандидат]" },
  helium_12m: { sku: "g1.play.helium", offer: "eft-12mo", note: "Plus 400 ГБ 12 месяцев бесплатно, затем $4.99/мес." },
  helium_6m: { sku: "g1.play.helium", offer: "eft-6mo", note: "Plus 400 ГБ 6 месяцев бесплатно, затем $4.99/мес." },
  helium_3m: { sku: "g1.play.helium", offer: "eft-3mo", note: "Plus 400 ГБ 3 месяца бесплатно, затем $4.99/мес." },
  helium_1m: { sku: "g1.play.helium", offer: "eft-1mo", note: "Plus 400 ГБ 1 месяц бесплатно, затем $4.99/мес." },
  helium_3m_75: { sku: "g1.helium.3months_ip_75p.acq", offer: "introprice", note: "$1.29 Plus 400 ГБ 3 месяца, затем $4.99/мес." },
  // ---- Plus 2 ТБ ----
  plus_2tb_base: { sku: "g1.2tb", offer: "", note: "Plus 2 ТБ базовый $9.99/мес." },
  plus_2tb_annual: { sku: "g1.2tb.annual", offer: "", note: "Plus 2 ТБ годовой $99.99/год." },
  plus_2tb_1m: { sku: "g1.2tb.1month_eft", offer: "freetrial", note: "Plus 2 ТБ 1 месяц бесплатно, затем $9.99/мес." },
  plus_2tb_3m: { sku: "g1.2tb.3months_eft", offer: "freetrial", note: "Plus 2 ТБ 3 месяца бесплатно, затем $9.99/мес." },
  plus_2tb_6m: { sku: "g1.2tb.6months_eft", offer: "freetrial", note: "Plus 2 ТБ 6 месяцев бесплатно, затем $9.99/мес." },
  plus_6m: { sku: "g1.2tb.subs_variant", offer: "6months-eft", note: "Plus 2 ТБ 6 месяцев бесплатно, затем $9.99/мес." },
  plus_3m: { sku: "g1.2tb.subs_variant", offer: "3months-eft", note: "Plus 2 ТБ 3 месяца бесплатно, затем $9.99/мес." },
  plus_2tb_85: { sku: "g1.2tb.3months_ip_85p.acq", offer: "introprice", note: "$1.49 Plus 2 ТБ 3 месяца, затем $9.99/мес." },
  // ---- Pro 5 ТБ ----
  pro_5tb_base: { sku: "g1.2tb.ai", offer: "", note: "Pro 5 ТБ базовый $19.99/мес., без триала." },
  pro_5tb_annual: { sku: "g1.2tb.ai.annual", offer: "", note: "Pro 5 ТБ годовой $219.99/год." },
  pro_5tb_alt_base: { sku: "g1.5tb", offer: "", note: "Pro 5 ТБ (alt) базовый $19.99/мес." },
  pro_5tb_alt_annual: { sku: "g1.5tb.annual", offer: "", note: "Pro 5 ТБ (alt) годовой $219.99/год." },
  pro_12m: { sku: "g1.2tb.ai.subs_variant", offer: "12months-eft", note: "Pro 5 ТБ 12 месяцев бесплатно, затем $19.99/мес." },
  pro_6m: { sku: "g1.2tb.ai.subs_variant", offer: "6months-eft", note: "Pro 5 ТБ 6 месяцев бесплатно, затем $19.99/мес." },
  pro_6m_2: { sku: "g1.2tb.ai.subs_variant", offer: "6months-eft-2", note: "Pro 5 ТБ 6 месяцев бесплатно (второй вариант, допускает продление), затем $19.99/мес." },
  pro_6m_ss: { sku: "g1.2tb.ai.subs_variant", offer: "6months-eft-ss-2026", note: "Pro 5 ТБ 6 месяцев бесплатно (SS 2026), затем $19.99/мес." },
  pro_play_3m: { sku: "g1.play.2tb.ai", offer: "eft-3mo", note: "Pro 5 ТБ 3 месяца бесплатно, затем $19.99/мес." },
  pro_3m_75: { sku: "g1.2tb.ai.3months_ip_75p.acq", offer: "introprice", note: "$4.99 Pro 5 ТБ 3 месяца, затем $19.99/мес." },
  // ---- Pro 10 ТБ ----
  pro10_base: { sku: "g1.10tb", offer: "", note: "Pro 10 ТБ базовый $49.99/мес." },
  pro10_annual: { sku: "g1.10tb.annual", offer: "", note: "Pro 10 ТБ годовой $499.99/год." },
  pro10_1m_90: { sku: "g1.10tb.1month_ip_90p", offer: "introprice", note: "$4.99 Pro 10 ТБ 1 месяц, затем $49.99/мес." },
  pro10_3m_85: { sku: "g1.10tb.3months_ip_85p", offer: "introprice", note: "$7.49 Pro 10 ТБ 3 месяца, затем $49.99/мес." },
  // ---- Ultra 5x 20 ТБ ----
  ultra5_base: { sku: "g1.20tb", offer: "", note: "Ultra 5x (20 ТБ) базовый $99.99/мес." },
  ultra5_base_v2: { sku: "g1.20tb.v2", offer: "", note: "Ultra 5x (20 ТБ) v2 базовый $99.99/мес." },
  ultra5_play_base: { sku: "g1.play.20tb", offer: "", note: "Ultra 5x (20 ТБ) Play базовый $99.99/мес." },
  ultra5x_12m: { sku: "g1.play.20tb", offer: "eft-12month", note: "Ultra 5x (20 ТБ) 12 месяцев бесплатно, затем $99.99/мес." },
  ultra5x_6m: { sku: "g1.play.20tb", offer: "eft-6month", note: "Ultra 5x (20 ТБ) 6 месяцев бесплатно, затем $99.99/мес." },
  ultra5x_3m: { sku: "g1.play.20tb", offer: "eft-3month", note: "Ultra 5x (20 ТБ) 3 месяца бесплатно, затем $99.99/мес." },
  ultra5x_1m: { sku: "g1.play.20tb", offer: "eft-1month", note: "Ultra 5x (20 ТБ) 1 месяц бесплатно, затем $99.99/мес." },
  ultra20_3m_90: { sku: "g1.20tb.3months_ip_90p.acq", offer: "introprice", note: "$9.99 Ultra 5x (20 ТБ) 3 месяца, затем $99.99/мес." },
  ultra20_3m_80: { sku: "g1.20tb.3months_ip_80p.acq", offer: "introprice", note: "$19.99 Ultra 5x (20 ТБ) 3 месяца, затем $99.99/мес." },
  ultra20_3m_75: { sku: "g1.20tb.3months_ip_75p.acq", offer: "introprice", note: "$24.99 Ultra 5x (20 ТБ) 3 месяца, затем $99.99/мес." },
  // ---- Ultra 20x 30 ТБ ----
  ultra30_base: { sku: "g1.30tb", offer: "", note: "Ultra 30 ТБ базовый $149.99/мес. [в большинстве регионов снят]" },
  ultra20_base: { sku: "g1.ai.pro", offer: "", note: "Ultra 20x (30 ТБ) базовый $199.99/мес., без триала (кнопка Upgrade в приложении)." },
  ultra20_play_base: { sku: "g1.play.ai.pro", offer: "", note: "Ultra 20x (30 ТБ) Play базовый $199.99/мес." },
  ultra20x_12m: { sku: "g1.play.ai.pro", offer: "eft-12mo", note: "Ultra 20x (30 ТБ) 12 месяцев бесплатно, затем $199.99/мес." },
  ultra20x_6m: { sku: "g1.play.ai.pro", offer: "eft-6mo", note: "Ultra 20x (30 ТБ) 6 месяцев бесплатно, затем $199.99/мес." },
  ultra20x_3m: { sku: "g1.play.ai.pro", offer: "eft-3mo", note: "Ultra 20x (30 ТБ) 3 месяца бесплатно, затем $199.99/мес." },
  ultra20x_1m: { sku: "g1.play.ai.pro", offer: "eft-1mo", note: "Ultra 20x (30 ТБ) 1 месяц бесплатно, затем $199.99/мес." },
  ultra_1m_90: { sku: "g1.ai.ultra.1month_ip_90p.acq", offer: "introprice", note: "$19.99 Ultra 20x (30 ТБ) 1 месяц, затем $199.99/мес." },
  ultra_3m_90: { sku: "g1.ai.ultra.3months_ip_90p.acq", offer: "introprice", note: "$19.99 Ultra 20x (30 ТБ) 3 месяца, затем $199.99/мес." },
  ultra_3m_80: { sku: "g1.ai.ultra.3months_ip_80p.acq", offer: "introprice", note: "$39.99 Ultra 20x (30 ТБ) 3 месяца, затем $199.99/мес." },
  ultra_1m_75: { sku: "g1.ai.ultra.1month_ip_75p.acq", offer: "introprice", note: "$49.99 Ultra 20x (30 ТБ) 1 месяц, затем $199.99/мес." },
  ultra_3m_75: { sku: "g1.ai.ultra.3months_ip_75p.acq", offer: "introprice", note: "$49.99 Ultra 20x (30 ТБ) 3 месяца, затем $199.99/мес." },
  // ---- YouTube Premium add-ons ----
  yt_1m: { sku: "g1.youtube_premium_individual_add_on", offer: "eft-1mo", note: "YouTube Premium (индивидуальный) 1 месяц бесплатно, затем $11.99/мес." },
  yt_family: { sku: "g1.youtube_premium_family_add_on", offer: "eft-1mo", note: "YouTube Premium (семейный) 1 месяц бесплатно" },
  yt_lite: { sku: "g1.youtube_premium_lite_add_on", offer: "eft-1mo", note: "YouTube Premium Lite 1 месяц бесплатно" },
  // ---- Кандидаты из scan_all.py (70) — не подтверждены в скане 21.11 ----
  cand_2tb_12m: { sku: "g1.2tb.12months_eft", offer: "freetrial", note: "[кандидат] Plus 2 ТБ 12 мес trial, затем $9.99/мес." },
  cand_20tb_1m: { sku: "g1.20tb.1month_eft", offer: "freetrial", note: "[кандидат] Ultra 20 ТБ 1 мес trial, затем $99.99/мес." },
  cand_20tb_12m: { sku: "g1.20tb.12months_eft", offer: "freetrial", note: "[кандидат] Ultra 20 ТБ 12 мес trial, затем $99.99/мес." },
  cand_30tb_1m: { sku: "g1.30tb.1month_eft", offer: "freetrial", note: "[кандидат] 30 ТБ 1 мес trial." },
  cand_30tb_12m: { sku: "g1.30tb.12months_eft", offer: "freetrial", note: "[кандидат] 30 ТБ 12 мес trial." },
  cand_ai: { sku: "g1.ai", offer: "", note: "[кандидат] AI, базовый." },
  cand_ai_plus: { sku: "g1.ai.plus", offer: "", note: "[кандидат] AI Plus, базовый." },
  cand_ai_ultra: { sku: "g1.ai.ultra", offer: "", note: "[кандидат] AI Ultra, базовый." },
  cand_5tb_ai: { sku: "g1.5tb.ai", offer: "", note: "[кандидат] Pro 5 ТБ ai, базовый $19.99/мес." },
  cand_20tb_ai: { sku: "g1.20tb.ai", offer: "", note: "[кандидат] Ultra 20 ТБ ai, базовый $99.99/мес." },
  cand_30tb_ai: { sku: "g1.30tb.ai", offer: "", note: "[кандидат] 30 ТБ ai, базовый." },
  cand_5tb_ai_subs: { sku: "g1.5tb.ai.subs_variant", offer: "", note: "[кандидат] Pro 5 ТБ ai subs_variant." },
  cand_20tb_ai_subs: { sku: "g1.20tb.ai.subs_variant", offer: "", note: "[кандидат] Ultra 20 ТБ ai subs_variant." },
  cand_30tb_ai_subs: { sku: "g1.30tb.ai.subs_variant", offer: "", note: "[кандидат] 30 ТБ ai subs_variant." },
  cand_play: { sku: "g1.play", offer: "", note: "[кандидат] Play, базовый." },
  cand_play_ai: { sku: "g1.play.ai", offer: "", note: "[кандидат] Play AI." },
  cand_play_2tb: { sku: "g1.play.2tb", offer: "", note: "[кандидат] Play 2 ТБ." },
  cand_play_5tb: { sku: "g1.play.5tb", offer: "", note: "[кандидат] Play 5 ТБ." },
  cand_play_30tb: { sku: "g1.play.30tb", offer: "", note: "[кандидат] Play 30 ТБ." },
  cand_play_ai_plus: { sku: "g1.play.ai.plus", offer: "", note: "[кандидат] Play AI Plus." },
  cand_play_ai_ultra: { sku: "g1.play.ai.ultra", offer: "", note: "[кандидат] Play AI Ultra." },
  cand_play_pro: { sku: "g1.play.pro", offer: "", note: "[кандидат] Play Pro." },
  cand_play_plus: { sku: "g1.play.plus", offer: "", note: "[кандидат] Play Plus." },
  cand_play_20tb_12m: { sku: "g1.play.20tb.12month", offer: "", note: "[кандидат] Play Ultra 20 ТБ 12 мес." },
  cand_play_ai_pro_12m: { sku: "g1.play.ai.pro.12month", offer: "", note: "[кандидат] Play Ultra 30 ТБ 12 мес." },
  cand_play_30tb_12m: { sku: "g1.play.30tb.12month", offer: "", note: "[кандидат] Play 30 ТБ 12 мес." },
  cand_play_5tb_12m: { sku: "g1.play.5tb.12month", offer: "", note: "[кандидат] Play 5 ТБ 12 мес." },
  cand_5tb_3m_75: { sku: "g1.5tb.3months_ip_75p.acq", offer: "introprice", note: "[кандидат] $ Pro 5 ТБ 3 мес introprice, затем $19.99/мес." },
  cand_100gb_3m_83: { sku: "g1.100gb.3months_ip_83p.acq", offer: "introprice", note: "[кандидат] Basic 100 ГБ 3 мес introprice 83%, затем $1.99/мес." },
  cand_200gb_3m_83: { sku: "g1.200gb.3months_ip_83p.acq", offer: "introprice", note: "[кандидат] Standard 200 ГБ 3 мес introprice 83%, затем $2.99/мес." },
  cand_30gb_3m_83: { sku: "g1.30gb.3months_ip_83p.acq", offer: "introprice", note: "[кандидат] Lite 30 ГБ 3 мес introprice 83%, затем $0.89/мес." },
  cand_helium_3m_83: { sku: "g1.helium.3months_ip_83p.acq", offer: "introprice", note: "[кандидат] Plus 400 ГБ 3 мес introprice 83%, затем $4.99/мес." },
  cand_home: { sku: "g1.home_premium", offer: "", note: "[кандидат] Home Premium add-on." },
  cand_health: { sku: "g1.health_premium", offer: "", note: "[кандидат] Health Premium add-on." },
  cand_play_home: { sku: "g1.play.home", offer: "", note: "[кандидат] Play Home add-on." },
  cand_play_health: { sku: "g1.play.health", offer: "", note: "[кандидат] Play Health add-on." },
  cand_ultra: { sku: "g1.ultra", offer: "", note: "[кандидат] Ultra." },
  cand_ultra_20tb: { sku: "g1.ultra.20tb", offer: "", note: "[кандидат] Ultra 20 ТБ." },
  cand_ultra_30tb: { sku: "g1.ultra.30tb", offer: "", note: "[кандидат] Ultra 30 ТБ." },
  cand_pro: { sku: "g1.pro", offer: "", note: "[кандидат] Pro." },
  cand_plus: { sku: "g1.plus", offer: "", note: "[кандидат] Plus." },
  cand_premium: { sku: "g1.premium", offer: "", note: "[кандидат] Premium." }
};

var STACK_MODE = 5; // Для продления используется CHARGE_FULL_PRICE
var DEX_PATHS = [
  "/data/local/tmp/module_521.apk",
  "/data/local/tmp/billing.apk"
];

var dexLoader = null;
var ctxRef = null;
var clientRef = null;
var booted = false;
var held = [];
function hold(x) { held.push(x); return x; }

function L(v) { Java.classFactory.loader = v; }
function clip(x) { try { var s = String(x); return s.length > 800 ? s.slice(0, 800) : s; } catch (e) { return "?"; } }
function keys() { var a = []; for (var k in PLANS) a.push(k); return a; }
function onJava(fn) {
  Java.perform(fn);
}
function planList() {
  var a = [];
  for (var k in PLANS) a.push({ id: k, sku: PLANS[k].sku, offer: PLANS[k].offer, note: PLANS[k].note });
  return a;
}
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
  console.log("[g1] " + bits.join("  "));
}

function getActivity() {
  L(null);
  var found = null, g1 = null;
  try {
    var th = Java.use("android.app.ActivityThread").currentActivityThread();
    var it = th.mActivities.value.values().iterator();
    while (it.hasNext()) {
      var rec = it.next();
      try {
        var act = rec.activity.value;
        if (!act || act.isFinishing()) continue;
        try { if (act.isDestroyed()) continue; } catch (e1) {}
        var paused = false;
        try { paused = rec.paused.value; } catch (e2) {}
        var name = String(act.getClass().getName());
        if (name.indexOf("subscriptions.red") >= 0) {
          g1 = act;
          if (!paused) found = act;
        }
        if (!found && !paused) found = act;
      } catch (e3) {}
    }
  } catch (e) { log("act_err", { m: clip(e) }); }
  if (!found) found = g1;
  if (!found) {
    try {
      Java.choose("android.app.Activity", {
        onMatch: function (a) { try { if (!found && !a.isFinishing()) found = a; } catch (e4) {} },
        onComplete: function () {}
      });
    } catch (e5) {}
  }
  return found;
}

function planOf(name) {
  var p = PLANS[name];
  if (!p) return null;
  return { name: name, sku: p.sku, offer: p.offer, note: p.note };
}

function isG1Sub(prods) {
  var s = String(prods || "");
  return s.indexOf("g1.") >= 0;
}

function pickOldToken(list) {
  var any = "", prefer = "";
  if (!list) return "";
  var Purchase = Java.use("com.android.billingclient.api.Purchase");
  for (var i = 0; i < list.size(); i++) {
    var pu = Java.cast(list.get(i), Purchase);
    var prods = String(pu.getProducts());
    var t = String(pu.getPurchaseToken() || "");
    log("old_purchase", { i: i, products: prods, head: t.slice(0, 16) });
    if (!t) continue;
    if (!any) any = t;
    if (isG1Sub(prods)) prefer = t;
  }
  return prefer || any;
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

function connectThen(fn) {
  L(dexLoader);
  var BillingClient = Java.use("com.android.billingclient.api.BillingClient");
  var PUL = Java.use("com.android.billingclient.api.PurchasesUpdatedListener");
  var Lst = Java.registerClass({
    name: "rc.PPA" + Date.now(),
    implements: [PUL],
    methods: {
      onPurchasesUpdated: function (r, p) {
        log("purchase_cb", { code: r.getResponseCode(), msg: String(r.getDebugMessage() || ""), n: p ? p.size() : 0 });
      }
    }
  });
  var b = BillingClient.newBuilder(ctxRef);
  b.setListener(hold(Lst.$new()));
  hold(Lst);
  try { b.enablePendingPurchases(); } catch (e) {}
  try {
    var PPP = Java.use("com.android.billingclient.api.PendingPurchasesParams");
    b.enablePendingPurchases(PPP.newBuilder().enableOneTimeProducts().build());
  } catch (e2) {}
  clientRef = b.build();
  var SLL = Java.use("com.android.billingclient.api.BillingClientStateListener");
  var SL = Java.registerClass({
    name: "rc.PPB" + Date.now(),
    implements: [SLL],
    methods: {
      onBillingSetupFinished: function (r) {
        log("setup", { code: r.getResponseCode(), msg: String(r.getDebugMessage() || "") });
        if (r.getResponseCode() === 0) fn();
      },
      onBillingServiceDisconnected: function () { log("disc", {}); }
    }
  });
  hold(SL);
  clientRef.startConnection(hold(SL.$new()));
}

function applyStackParams(builder, oldTok) {
  var SUP = Java.use("com.android.billingclient.api.BillingFlowParams$SubscriptionUpdateParams");
  var sb = SUP.newBuilder();
  var modeSet = false;
  try { sb = sb.setReplacementMode(STACK_MODE); modeSet = true; } catch (e0) {}
  if (!modeSet) {
    try { sb = sb.setReplaceProrationMode(STACK_MODE); modeSet = true; } catch (e1) {}
  }
  if (!modeSet) {
    try { sb = sb.setReplaceSkusProrationMode(STACK_MODE); modeSet = true; } catch (e2) {
      log("mode_err", { m: clip(e2) });
    }
  }
  log("mode_applied", { mode: STACK_MODE, ok: modeSet });
  builder = builder.setSubscriptionUpdateParams(sb.setOldPurchaseToken(String(oldTok)).build());
  log("stack_mode", { mode: STACK_MODE, old: String(oldTok).slice(0, 16) });
  return builder;
}

function launchFlow(hit, hitOffer, add, addOffer, oldTok, spec) {
  L(dexLoader);
  var PDP = Java.use("com.android.billingclient.api.BillingFlowParams$ProductDetailsParams");
  var BFP = Java.use("com.android.billingclient.api.BillingFlowParams");
  var l = Java.use("java.util.ArrayList").$new();
  var tok = String(hitOffer.getOfferToken());
  log("use_token", {
    n: tok.length,
    sku: spec.sku,
    offer: spec.offer,
    target: spec.name,
    addon: ADDON || "",
    stack: !!oldTok
  });
  l.add(PDP.newBuilder().setProductDetails(hit).setOfferToken(tok).build());
  if (add && addOffer && String(add.getProductId()) !== spec.sku) {
    l.add(PDP.newBuilder().setProductDetails(add).setOfferToken(String(addOffer.getOfferToken())).build());
    log("addon", { sku: String(add.getProductId()), offer: String(addOffer.getOfferId() || "") });
  }
  var b = BFP.newBuilder().setProductDetailsParamsList(l);
  if (oldTok) {
    try { b = applyStackParams(b, oldTok); } catch (e) { log("stack_param_err", { m: clip(e) }); }
  }
  var params = b.build();
  L(null);
  var Handler = Java.use("android.os.Handler");
  var Looper = Java.use("android.os.Looper");
  var tries = [0];
  var R = Java.registerClass({
    name: "rc.PPR" + Date.now(),
    implements: [Java.use("java.lang.Runnable")],
    methods: {
      run: function () {
        try {
          var act = getActivity();
          log("activity", { a: act ? String(act.getClass().getName()) : "null", try: tries[0] });
          if (!act) {
            if (tries[0] < 8) {
              tries[0] += 1;
              Handler.$new(Looper.getMainLooper()).postDelayed(R.$new(), 400);
              return;
            }
            log("no_activity", {});
            return;
          }
          L(dexLoader);
          var Activity = Java.use("android.app.Activity");
          var r2 = clientRef.launchBillingFlow(Java.cast(act, Activity), params);
          log("launched", { code: r2.getResponseCode(), msg: String(r2.getDebugMessage() || "") });
        } catch (e) { log("launch_err", { m: clip(e) }); }
      }
    }
  });
  hold(R);
  Handler.$new(Looper.getMainLooper()).post(hold(R.$new()));
}

function shOut(argv) {
  L(null);
  var ArrayList = Java.use("java.util.ArrayList");
  var args = ArrayList.$new();
  for (var i = 0; i < argv.length; i++) args.add(argv[i]);
  var pb = Java.use("java.lang.ProcessBuilder").$new(args);
  pb.redirectErrorStream(true);
  var proc = pb.start();
  var br = Java.use("java.io.BufferedReader").$new(Java.use("java.io.InputStreamReader").$new(proc.getInputStream()));
  var out = "";
  var line;
  while (true) {
    line = br.readLine();
    if (line === null) break;
    out += String(line) + "\n";
  }
  proc.waitFor();
  L(dexLoader);
  return out;
}

function tokenFromPlayDb() {
  try {
    var sql = "select inapp_purchase_data from ownership where doc_id like '%g1.2tb.ai%' or doc_id like '%g1.play.2tb.ai%' order by subs_valid_until_time desc limit 5;";
    var out = shOut(["su", "0", "sqlite3", "/data/data/com.android.vending/databases/library.db", sql]);
    var m = out.match(/"purchaseToken"\s*:\s*"([^"]+)"/);
    if (m && m[1]) {
      log("old_purchase", { i: 0, products: "library.db", head: m[1].slice(0, 16) });
      return m[1];
    }
    log("library_miss", { n: out.length });
  } catch (e) { log("library_err", { m: clip(e) }); }
  return "";
}

function queryPurchasesThen(cb) {
  L(dexLoader);
  var dbTok = tokenFromPlayDb();
  if (dbTok) { cb(dbTok); return; }
  try {
    var pr = clientRef.queryPurchases("subs");
    var list = pr.getPurchasesList();
    log("purchases_sync", { n: list ? list.size() : -1, code: String(pr.getResponseCode()) });
    cb(pickOldToken(list));
    return;
  } catch (e) { log("purchases_sync_err", { m: clip(e) }); }
  var PRL = Java.use("com.android.billingclient.api.PurchasesResponseListener");
  var cls = hold(Java.registerClass({
    name: "rc.PPS" + Date.now(),
    implements: [PRL],
    methods: {
      onQueryPurchasesResponse: function (br, purchases) {
        try {
          var list2 = Java.cast(purchases, Java.use("java.util.List"));
          log("purchases", { n: list2.size(), code: String(br.getResponseCode()) });
          cb(pickOldToken(list2));
        } catch (e2) { log("stack_query_err", { m: clip(e2) }); }
      }
    }
  }));
  var listener = hold(cls.$new());
  var Handler = Java.use("android.os.Handler");
  var Looper = Java.use("android.os.Looper");
  var Rq = hold(Java.registerClass({
    name: "rc.PPQ" + Date.now(),
    implements: [Java.use("java.lang.Runnable")],
    methods: {
      run: function () {
        try {
          var QP = Java.use("com.android.billingclient.api.QueryPurchasesParams");
          clientRef.queryPurchasesAsync(QP.newBuilder().setProductType("subs").build(), listener);
          log("purchases_async", { via: "params-main" });
        } catch (e3) {
          try {
            clientRef.queryPurchasesAsync("subs", listener);
            log("purchases_async", { via: "skuType-main" });
          } catch (e4) { log("purchases_sku_err", { m: clip(e4) }); }
        }
      }
    }
  }));
  Handler.$new(Looper.getMainLooper()).post(hold(Rq.$new()));
}

function queryOfferThen(spec, oldTok) {
  L(dexLoader);
  var Prod = Java.use("com.android.billingclient.api.QueryProductDetailsParams$Product");
  var Params = Java.use("com.android.billingclient.api.QueryProductDetailsParams");
  var PDL = Java.use("com.android.billingclient.api.ProductDetailsResponseListener");
  var addon = ADDON && PLANS[ADDON] ? PLANS[ADDON] : null;
  var PL = Java.registerClass({
    name: "rc.PPC" + Date.now(),
    implements: [PDL],
    methods: {
      onProductDetailsResponse: function (res, list) {
        log("pd", { code: res.getResponseCode(), n: list ? list.size() : 0, msg: String(res.getDebugMessage() || "") });
        if (res.getResponseCode() !== 0 || !list) { log("done", {}); return; }
        L(dexLoader);
        var PD = Java.use("com.android.billingclient.api.ProductDetails");
        var SOD = Java.use("com.android.billingclient.api.ProductDetails$SubscriptionOfferDetails");
        var hit = null, hitOffer = null, add = null, addOffer = null;
        for (var i = 0; i < list.size(); i++) {
          var pd = Java.cast(list.get(i), PD);
          var pid = String(pd.getProductId());
          log("product", { id: pid, title: String(pd.getTitle() || "") });
          var offs = pd.getSubscriptionOfferDetails();
          if (!offs) continue;
          for (var j = 0; j < offs.size(); j++) {
            var o = Java.cast(offs.get(j), SOD);
            var oid = String(o.getOfferId() || "");
            log("offer", { product: pid, offerId: oid, token: String(o.getOfferToken() || "").slice(0, 12) + "..." });
            if (pid === spec.sku && oid === spec.offer) { hit = pd; hitOffer = o; }
            if (addon && pid === addon.sku && oid === addon.offer) { add = pd; addOffer = o; }
          }
        }
        if (!hit || !hitOffer) { log("no_offer", { sku: spec.sku, offer: spec.offer, target: spec.name }); return; }
        if (ADDON && (!add || !addOffer)) log("no_addon", { addon: ADDON });
        if (oldTok) log("stack_start", { src: "old_token", sku: spec.sku, offer: spec.offer });
        launchFlow(hit, hitOffer, add, addOffer, oldTok || "", spec);
      }
    }
  });
  var arr = Java.use("java.util.ArrayList").$new();
  var seen = {};
  function addSku(sku) {
    if (!sku || seen[sku]) return;
    seen[sku] = 1;
    arr.add(Prod.newBuilder().setProductId(sku).setProductType("subs").build());
  }
  addSku(spec.sku);
  if (addon) addSku(addon.sku);
  hold(PL);
  clientRef.queryProductDetailsAsync(Params.newBuilder().setProductList(arr).build(), hold(PL.$new()));
  log("query_sent", { n: arr.size(), sku: spec.sku, offer: spec.offer });
}

function run(target, stack) {
  var spec = planOf(target);
  if (!spec) { log("bad_target", { target: target, keys: keys().join(",") }); return; }
  TARGET = spec.name;
  STACK = !!stack;
  log("perform", {
    target: spec.name, sku: spec.sku, offer: spec.offer, note: spec.note,
    stack: STACK, mode: STACK ? "renew" : "new"
  });
  if (!clientRef) {
    log("boot_err", { m: "BillingClient not ready" });
    return;
  }
  if (STACK) {
    queryPurchasesThen(function (tok) {
      if (!tok) { log("no_purchase", { m: "У текущего аккаунта нет подписки, подходящей для продления" }); return; }
      queryOfferThen(spec, tok);
    });
  } else {
    queryOfferThen(spec, "");
  }
}

function boot() {
  if (booted && clientRef) {
    log("ready", { plans: keys().length, reused: true });
    return;
  }
  if (!loadBilling()) return;
  connectThen(function () {
    booted = true;
    log("ready", { plans: keys().length, reused: false });
  });
}

rpc.exports = {
  plans: function () { return planList(); },
  status: function () {
    return { booted: booted, target: TARGET, stack: STACK, addon: ADDON };
  },
  setAddon: function (name) {
    ADDON = name || "";
    log("addon_set", { addon: ADDON });
    return ADDON;
  },
  buy: function (name) {
    var t = name || TARGET;
    onJava(function () { run(t, false); });
    return "buy " + t;
  },
  stack: function (name) {
    var t = name || TARGET;
    onJava(function () { run(t, true); });
    return "stack " + t;
  }
};

recv("cfg", function onCfg(msg) {
  var p = (msg && msg.payload) ? msg.payload : (msg || {});
  TARGET = p.target || TARGET;
  STACK = !!p.stack;
  if (p.addon !== undefined) ADDON = p.addon || "";
  onJava(function () { run(TARGET, STACK); });
  recv("cfg", onCfg);
});

var scriptStarted = false;
setImmediate(function () {
  onJava(function () {
    if (scriptStarted) return;
    scriptStarted = true;
    log("script_start", { plans: keys().length });
    boot();
  });
});
