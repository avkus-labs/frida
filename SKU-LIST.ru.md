# Список SKU Google One

Полный каталог тарифов из `frida.js` — тот же список, что в веб-артефакте,
только в формате GitHub Markdown: таблицы по тарифам и списки для копирования.

**Всего: 109 записей, 94 уникальных SKU. Подтверждённых: 66, кандидатов: 43.**
Дата: 22.11.2026. Источник истины — `frida.js` (`var PLANS`); этот файл сгенерирован
из него скриптом, руками ничего не вписано, так что расхождений быть не должно.

## Как читать

- **SKU** — `productId` в Google Play Billing, то, что уходит в `queryProductDetailsAsync`.
- **Offer** — `offerId`. Пустой offer (`""`) — это базовый план: в BillingClient
  у него `offerId` равен `null`, в скрипте он превращается в пустую строку.
- **Бесплатно** — первый период $0, потом цена из примечания. Триал даётся один раз
  на аккаунт, и `launchBillingFlow` может сжечь право на триал, даже если не нажать
  «Подписаться». Триал сам продлевается в платный — отменять заранее.
- **[кандидат]** — SKU из пула перебора `scan_all.py` (70 штук), в живом скане
  21.11.2026 он не ответил. Скорее всего мёртвый, проверять только живым запросом:
  если Play вернул `no_offer` — кода для этого аккаунта/региона нет.
- Цены — доллары США из `frida.js`. В Европе те же тарифы в евро дороже
  (например, Pro 5 ТБ — $19.99 в США и €21.99 в ЕС).

## Главное про Ultra — не перепутать SKU

- Ultra 5x, 20 ТБ, $99.99/мес.: бесплатные триалы — только на **`g1.play.20tb`**
  (`eft-12month / eft-6month / eft-3month / eft-1month`). Базовый `g1.20tb` триала не даёт.
- Ultra 20x, 30 ТБ, $199.99/мес.: бесплатные триалы — только на **`g1.play.ai.pro`**
  (`eft-12mo / eft-6mo / eft-3mo / eft-1mo`). **`g1.ai.pro`** — тот же 30 ТБ за $199.99,
  но без триала: именно его жмёт кнопка Upgrade в приложении. `g1.30tb` — отдельный
  30 ТБ за $149.99, тоже без триала, в большинстве регионов уже снят.

## Lite 30 ГБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `lite_base` | `g1.30gb` | `` | Lite 30 ГБ базовый $0.89/мес. |
| `lite_annual` | `g1.30gb.annual` | `` | Lite 30 ГБ годовой $8.99/год. |
| `lite_1m` | `g1.30gb.1month_eft` | `eft-1month` | Lite 30 ГБ 1 месяц бесплатно, затем $0.89/мес. |
| `lite_3m_85` | `g1.30gb.3months_ip_85p.acq` | `introprice` | $0.15 Lite 30 ГБ 3 месяца, затем $0.89/мес. |

## Basic 100 ГБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `basic_base` | `g1.100gb` | `` | Basic 100 ГБ базовый $1.99/мес. |
| `basic_annual` | `g1.100gb.annual` | `` | Basic 100 ГБ годовой $19.99/год. |
| `basic_1m` | `g1.100gb.1month_eft` | `freetrial` | Basic 100 ГБ 1 месяц бесплатно, затем $1.99/мес. |
| `basic_3m` | `g1.100gb.3months_eft` | `freetrial` | Basic 100 ГБ 3 месяца бесплатно, затем $1.99/мес. |
| `basic_3m_85` | `g1.100gb.3months_ip_85p.acq` | `introprice` | $0.29 Basic 100 ГБ 3 месяца, затем $1.99/мес. |

## Standard 200 ГБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `std_base` | `g1.200gb` | `` | Standard 200 ГБ базовый $2.99/мес. |
| `std_annual` | `g1.200gb.annual` | `` | Standard 200 ГБ годовой $29.99/год. |
| `std_1m` | `g1.200gb.1month_eft` | `freetrial` | Standard 200 ГБ 1 месяц бесплатно, затем $2.99/мес. |
| `std_3m` | `g1.200gb.3months_eft` | `freetrial` | Standard 200 ГБ 3 месяца бесплатно, затем $2.99/мес. |
| `std_3m_85` | `g1.200gb.3months_ip_85p.acq` | `introprice` | $0.49 Standard 200 ГБ 3 месяца, затем $2.99/мес. |

## Plus 400 ГБ (helium)

| План | SKU | Offer | Что это |
|---|---|---|---|
| `helium_base` | `g1.helium` | `` | Plus 400 ГБ базовый $4.99/мес. [кандидат] |
| `helium_12m` | `g1.play.helium` | `eft-12mo` | Plus 400 ГБ 12 месяцев бесплатно, затем $4.99/мес. |
| `helium_6m` | `g1.play.helium` | `eft-6mo` | Plus 400 ГБ 6 месяцев бесплатно, затем $4.99/мес. |
| `helium_3m` | `g1.play.helium` | `eft-3mo` | Plus 400 ГБ 3 месяца бесплатно, затем $4.99/мес. |
| `helium_1m` | `g1.play.helium` | `eft-1mo` | Plus 400 ГБ 1 месяц бесплатно, затем $4.99/мес. |
| `helium_3m_75` | `g1.helium.3months_ip_75p.acq` | `introprice` | $1.29 Plus 400 ГБ 3 месяца, затем $4.99/мес. |

## Plus 2 ТБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `plus_2tb_base` | `g1.2tb` | `` | Plus 2 ТБ базовый $9.99/мес. |
| `plus_2tb_annual` | `g1.2tb.annual` | `` | Plus 2 ТБ годовой $99.99/год. |
| `plus_2tb_1m` | `g1.2tb.1month_eft` | `freetrial` | Plus 2 ТБ 1 месяц бесплатно, затем $9.99/мес. |
| `plus_2tb_3m` | `g1.2tb.3months_eft` | `freetrial` | Plus 2 ТБ 3 месяца бесплатно, затем $9.99/мес. |
| `plus_2tb_6m` | `g1.2tb.6months_eft` | `freetrial` | Plus 2 ТБ 6 месяцев бесплатно, затем $9.99/мес. |
| `plus_6m` | `g1.2tb.subs_variant` | `6months-eft` | Plus 2 ТБ 6 месяцев бесплатно, затем $9.99/мес. |
| `plus_3m` | `g1.2tb.subs_variant` | `3months-eft` | Plus 2 ТБ 3 месяца бесплатно, затем $9.99/мес. |
| `plus_2tb_85` | `g1.2tb.3months_ip_85p.acq` | `introprice` | $1.49 Plus 2 ТБ 3 месяца, затем $9.99/мес. |

## Pro 5 ТБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `pro_5tb_base` | `g1.2tb.ai` | `` | Pro 5 ТБ базовый $19.99/мес., без триала. |
| `pro_5tb_annual` | `g1.2tb.ai.annual` | `` | Pro 5 ТБ годовой $219.99/год. |
| `pro_5tb_alt_base` | `g1.5tb` | `` | Pro 5 ТБ (alt) базовый $19.99/мес. |
| `pro_5tb_alt_annual` | `g1.5tb.annual` | `` | Pro 5 ТБ (alt) годовой $219.99/год. |
| `pro_12m` | `g1.2tb.ai.subs_variant` | `12months-eft` | Pro 5 ТБ 12 месяцев бесплатно, затем $19.99/мес. |
| `pro_6m` | `g1.2tb.ai.subs_variant` | `6months-eft` | Pro 5 ТБ 6 месяцев бесплатно, затем $19.99/мес. |
| `pro_6m_2` | `g1.2tb.ai.subs_variant` | `6months-eft-2` | Pro 5 ТБ 6 месяцев бесплатно (второй вариант, допускает продление), затем $19.99/мес. |
| `pro_6m_ss` | `g1.2tb.ai.subs_variant` | `6months-eft-ss-2026` | Pro 5 ТБ 6 месяцев бесплатно (SS 2026), затем $19.99/мес. |
| `pro_play_3m` | `g1.play.2tb.ai` | `eft-3mo` | Pro 5 ТБ 3 месяца бесплатно, затем $19.99/мес. |
| `pro_3m_75` | `g1.2tb.ai.3months_ip_75p.acq` | `introprice` | $4.99 Pro 5 ТБ 3 месяца, затем $19.99/мес. |

## Pro 10 ТБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `pro10_base` | `g1.10tb` | `` | Pro 10 ТБ базовый $49.99/мес. |
| `pro10_annual` | `g1.10tb.annual` | `` | Pro 10 ТБ годовой $499.99/год. |
| `pro10_1m_90` | `g1.10tb.1month_ip_90p` | `introprice` | $4.99 Pro 10 ТБ 1 месяц, затем $49.99/мес. |
| `pro10_3m_85` | `g1.10tb.3months_ip_85p` | `introprice` | $7.49 Pro 10 ТБ 3 месяца, затем $49.99/мес. |

## Ultra 5x 20 ТБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `ultra5_base` | `g1.20tb` | `` | Ultra 5x (20 ТБ) базовый $99.99/мес. |
| `ultra5_base_v2` | `g1.20tb.v2` | `` | Ultra 5x (20 ТБ) v2 базовый $99.99/мес. |
| `ultra5_play_base` | `g1.play.20tb` | `` | Ultra 5x (20 ТБ) Play базовый $99.99/мес. |
| `ultra5x_12m` | `g1.play.20tb` | `eft-12month` | Ultra 5x (20 ТБ) 12 месяцев бесплатно, затем $99.99/мес. |
| `ultra5x_6m` | `g1.play.20tb` | `eft-6month` | Ultra 5x (20 ТБ) 6 месяцев бесплатно, затем $99.99/мес. |
| `ultra5x_3m` | `g1.play.20tb` | `eft-3month` | Ultra 5x (20 ТБ) 3 месяца бесплатно, затем $99.99/мес. |
| `ultra5x_1m` | `g1.play.20tb` | `eft-1month` | Ultra 5x (20 ТБ) 1 месяц бесплатно, затем $99.99/мес. |
| `ultra20_3m_90` | `g1.20tb.3months_ip_90p.acq` | `introprice` | $9.99 Ultra 5x (20 ТБ) 3 месяца, затем $99.99/мес. |
| `ultra20_3m_80` | `g1.20tb.3months_ip_80p.acq` | `introprice` | $19.99 Ultra 5x (20 ТБ) 3 месяца, затем $99.99/мес. |
| `ultra20_3m_75` | `g1.20tb.3months_ip_75p.acq` | `introprice` | $24.99 Ultra 5x (20 ТБ) 3 месяца, затем $99.99/мес. |

## Ultra 20x 30 ТБ

| План | SKU | Offer | Что это |
|---|---|---|---|
| `ultra30_base` | `g1.30tb` | `` | Ultra 30 ТБ базовый $149.99/мес. [в большинстве регионов снят] |
| `ultra20_base` | `g1.ai.pro` | `` | Ultra 20x (30 ТБ) базовый $199.99/мес., без триала (кнопка Upgrade в приложении). |
| `ultra20_play_base` | `g1.play.ai.pro` | `` | Ultra 20x (30 ТБ) Play базовый $199.99/мес. |
| `ultra20x_12m` | `g1.play.ai.pro` | `eft-12mo` | Ultra 20x (30 ТБ) 12 месяцев бесплатно, затем $199.99/мес. |
| `ultra20x_6m` | `g1.play.ai.pro` | `eft-6mo` | Ultra 20x (30 ТБ) 6 месяцев бесплатно, затем $199.99/мес. |
| `ultra20x_3m` | `g1.play.ai.pro` | `eft-3mo` | Ultra 20x (30 ТБ) 3 месяца бесплатно, затем $199.99/мес. |
| `ultra20x_1m` | `g1.play.ai.pro` | `eft-1mo` | Ultra 20x (30 ТБ) 1 месяц бесплатно, затем $199.99/мес. |
| `ultra_1m_90` | `g1.ai.ultra.1month_ip_90p.acq` | `introprice` | $19.99 Ultra 20x (30 ТБ) 1 месяц, затем $199.99/мес. |
| `ultra_3m_90` | `g1.ai.ultra.3months_ip_90p.acq` | `introprice` | $19.99 Ultra 20x (30 ТБ) 3 месяца, затем $199.99/мес. |
| `ultra_3m_80` | `g1.ai.ultra.3months_ip_80p.acq` | `introprice` | $39.99 Ultra 20x (30 ТБ) 3 месяца, затем $199.99/мес. |
| `ultra_1m_75` | `g1.ai.ultra.1month_ip_75p.acq` | `introprice` | $49.99 Ultra 20x (30 ТБ) 1 месяц, затем $199.99/мес. |
| `ultra_3m_75` | `g1.ai.ultra.3months_ip_75p.acq` | `introprice` | $49.99 Ultra 20x (30 ТБ) 3 месяца, затем $199.99/мес. |

## YouTube Premium add-ons

| План | SKU | Offer | Что это |
|---|---|---|---|
| `yt_1m` | `g1.youtube_premium_individual_add_on` | `eft-1mo` | YouTube Premium (индивидуальный) 1 месяц бесплатно, затем $11.99/мес. |
| `yt_family` | `g1.youtube_premium_family_add_on` | `eft-1mo` | YouTube Premium (семейный) 1 месяц бесплатно |
| `yt_lite` | `g1.youtube_premium_lite_add_on` | `eft-1mo` | YouTube Premium Lite 1 месяц бесплатно |

## Кандидаты из scan_all.py (70) — не подтверждены в скане 21.11

| План | SKU | Offer | Что это |
|---|---|---|---|
| `cand_2tb_12m` | `g1.2tb.12months_eft` | `freetrial` | [кандидат] Plus 2 ТБ 12 мес trial, затем $9.99/мес. |
| `cand_20tb_1m` | `g1.20tb.1month_eft` | `freetrial` | [кандидат] Ultra 20 ТБ 1 мес trial, затем $99.99/мес. |
| `cand_20tb_12m` | `g1.20tb.12months_eft` | `freetrial` | [кандидат] Ultra 20 ТБ 12 мес trial, затем $99.99/мес. |
| `cand_30tb_1m` | `g1.30tb.1month_eft` | `freetrial` | [кандидат] 30 ТБ 1 мес trial. |
| `cand_30tb_12m` | `g1.30tb.12months_eft` | `freetrial` | [кандидат] 30 ТБ 12 мес trial. |
| `cand_ai` | `g1.ai` | `` | [кандидат] AI, базовый. |
| `cand_ai_plus` | `g1.ai.plus` | `` | [кандидат] AI Plus, базовый. |
| `cand_ai_ultra` | `g1.ai.ultra` | `` | [кандидат] AI Ultra, базовый. |
| `cand_5tb_ai` | `g1.5tb.ai` | `` | [кандидат] Pro 5 ТБ ai, базовый $19.99/мес. |
| `cand_20tb_ai` | `g1.20tb.ai` | `` | [кандидат] Ultra 20 ТБ ai, базовый $99.99/мес. |
| `cand_30tb_ai` | `g1.30tb.ai` | `` | [кандидат] 30 ТБ ai, базовый. |
| `cand_5tb_ai_subs` | `g1.5tb.ai.subs_variant` | `` | [кандидат] Pro 5 ТБ ai subs_variant. |
| `cand_20tb_ai_subs` | `g1.20tb.ai.subs_variant` | `` | [кандидат] Ultra 20 ТБ ai subs_variant. |
| `cand_30tb_ai_subs` | `g1.30tb.ai.subs_variant` | `` | [кандидат] 30 ТБ ai subs_variant. |
| `cand_play` | `g1.play` | `` | [кандидат] Play, базовый. |
| `cand_play_ai` | `g1.play.ai` | `` | [кандидат] Play AI. |
| `cand_play_2tb` | `g1.play.2tb` | `` | [кандидат] Play 2 ТБ. |
| `cand_play_5tb` | `g1.play.5tb` | `` | [кандидат] Play 5 ТБ. |
| `cand_play_30tb` | `g1.play.30tb` | `` | [кандидат] Play 30 ТБ. |
| `cand_play_ai_plus` | `g1.play.ai.plus` | `` | [кандидат] Play AI Plus. |
| `cand_play_ai_ultra` | `g1.play.ai.ultra` | `` | [кандидат] Play AI Ultra. |
| `cand_play_pro` | `g1.play.pro` | `` | [кандидат] Play Pro. |
| `cand_play_plus` | `g1.play.plus` | `` | [кандидат] Play Plus. |
| `cand_play_20tb_12m` | `g1.play.20tb.12month` | `` | [кандидат] Play Ultra 20 ТБ 12 мес. |
| `cand_play_ai_pro_12m` | `g1.play.ai.pro.12month` | `` | [кандидат] Play Ultra 30 ТБ 12 мес. |
| `cand_play_30tb_12m` | `g1.play.30tb.12month` | `` | [кандидат] Play 30 ТБ 12 мес. |
| `cand_play_5tb_12m` | `g1.play.5tb.12month` | `` | [кандидат] Play 5 ТБ 12 мес. |
| `cand_5tb_3m_75` | `g1.5tb.3months_ip_75p.acq` | `introprice` | [кандидат] $ Pro 5 ТБ 3 мес introprice, затем $19.99/мес. |
| `cand_100gb_3m_83` | `g1.100gb.3months_ip_83p.acq` | `introprice` | [кандидат] Basic 100 ГБ 3 мес introprice 83%, затем $1.99/мес. |
| `cand_200gb_3m_83` | `g1.200gb.3months_ip_83p.acq` | `introprice` | [кандидат] Standard 200 ГБ 3 мес introprice 83%, затем $2.99/мес. |
| `cand_30gb_3m_83` | `g1.30gb.3months_ip_83p.acq` | `introprice` | [кандидат] Lite 30 ГБ 3 мес introprice 83%, затем $0.89/мес. |
| `cand_helium_3m_83` | `g1.helium.3months_ip_83p.acq` | `introprice` | [кандидат] Plus 400 ГБ 3 мес introprice 83%, затем $4.99/мес. |
| `cand_home` | `g1.home_premium` | `` | [кандидат] Home Premium add-on. |
| `cand_health` | `g1.health_premium` | `` | [кандидат] Health Premium add-on. |
| `cand_play_home` | `g1.play.home` | `` | [кандидат] Play Home add-on. |
| `cand_play_health` | `g1.play.health` | `` | [кандидат] Play Health add-on. |
| `cand_ultra` | `g1.ultra` | `` | [кандидат] Ultra. |
| `cand_ultra_20tb` | `g1.ultra.20tb` | `` | [кандидат] Ultra 20 ТБ. |
| `cand_ultra_30tb` | `g1.ultra.30tb` | `` | [кандидат] Ultra 30 ТБ. |
| `cand_pro` | `g1.pro` | `` | [кандидат] Pro. |
| `cand_plus` | `g1.plus` | `` | [кандидат] Plus. |
| `cand_premium` | `g1.premium` | `` | [кандидат] Premium. |

## Только бесплатные ($0) — подтверждённые

| План | SKU | Offer | Что это |
|---|---|---|---|
| `lite_1m` | `g1.30gb.1month_eft` | `eft-1month` | Lite 30 ГБ 1 месяц бесплатно, затем $0.89/мес. |
| `basic_1m` | `g1.100gb.1month_eft` | `freetrial` | Basic 100 ГБ 1 месяц бесплатно, затем $1.99/мес. |
| `basic_3m` | `g1.100gb.3months_eft` | `freetrial` | Basic 100 ГБ 3 месяца бесплатно, затем $1.99/мес. |
| `std_1m` | `g1.200gb.1month_eft` | `freetrial` | Standard 200 ГБ 1 месяц бесплатно, затем $2.99/мес. |
| `std_3m` | `g1.200gb.3months_eft` | `freetrial` | Standard 200 ГБ 3 месяца бесплатно, затем $2.99/мес. |
| `helium_12m` | `g1.play.helium` | `eft-12mo` | Plus 400 ГБ 12 месяцев бесплатно, затем $4.99/мес. |
| `helium_6m` | `g1.play.helium` | `eft-6mo` | Plus 400 ГБ 6 месяцев бесплатно, затем $4.99/мес. |
| `helium_3m` | `g1.play.helium` | `eft-3mo` | Plus 400 ГБ 3 месяца бесплатно, затем $4.99/мес. |
| `helium_1m` | `g1.play.helium` | `eft-1mo` | Plus 400 ГБ 1 месяц бесплатно, затем $4.99/мес. |
| `plus_2tb_1m` | `g1.2tb.1month_eft` | `freetrial` | Plus 2 ТБ 1 месяц бесплатно, затем $9.99/мес. |
| `plus_2tb_3m` | `g1.2tb.3months_eft` | `freetrial` | Plus 2 ТБ 3 месяца бесплатно, затем $9.99/мес. |
| `plus_2tb_6m` | `g1.2tb.6months_eft` | `freetrial` | Plus 2 ТБ 6 месяцев бесплатно, затем $9.99/мес. |
| `plus_6m` | `g1.2tb.subs_variant` | `6months-eft` | Plus 2 ТБ 6 месяцев бесплатно, затем $9.99/мес. |
| `plus_3m` | `g1.2tb.subs_variant` | `3months-eft` | Plus 2 ТБ 3 месяца бесплатно, затем $9.99/мес. |
| `pro_12m` | `g1.2tb.ai.subs_variant` | `12months-eft` | Pro 5 ТБ 12 месяцев бесплатно, затем $19.99/мес. |
| `pro_6m` | `g1.2tb.ai.subs_variant` | `6months-eft` | Pro 5 ТБ 6 месяцев бесплатно, затем $19.99/мес. |
| `pro_6m_2` | `g1.2tb.ai.subs_variant` | `6months-eft-2` | Pro 5 ТБ 6 месяцев бесплатно (второй вариант, допускает продление), затем $19.99/мес. |
| `pro_6m_ss` | `g1.2tb.ai.subs_variant` | `6months-eft-ss-2026` | Pro 5 ТБ 6 месяцев бесплатно (SS 2026), затем $19.99/мес. |
| `pro_play_3m` | `g1.play.2tb.ai` | `eft-3mo` | Pro 5 ТБ 3 месяца бесплатно, затем $19.99/мес. |
| `ultra5x_12m` | `g1.play.20tb` | `eft-12month` | Ultra 5x (20 ТБ) 12 месяцев бесплатно, затем $99.99/мес. |
| `ultra5x_6m` | `g1.play.20tb` | `eft-6month` | Ultra 5x (20 ТБ) 6 месяцев бесплатно, затем $99.99/мес. |
| `ultra5x_3m` | `g1.play.20tb` | `eft-3month` | Ultra 5x (20 ТБ) 3 месяца бесплатно, затем $99.99/мес. |
| `ultra5x_1m` | `g1.play.20tb` | `eft-1month` | Ultra 5x (20 ТБ) 1 месяц бесплатно, затем $99.99/мес. |
| `ultra20x_12m` | `g1.play.ai.pro` | `eft-12mo` | Ultra 20x (30 ТБ) 12 месяцев бесплатно, затем $199.99/мес. |
| `ultra20x_6m` | `g1.play.ai.pro` | `eft-6mo` | Ultra 20x (30 ТБ) 6 месяцев бесплатно, затем $199.99/мес. |
| `ultra20x_3m` | `g1.play.ai.pro` | `eft-3mo` | Ultra 20x (30 ТБ) 3 месяца бесплатно, затем $199.99/мес. |
| `ultra20x_1m` | `g1.play.ai.pro` | `eft-1mo` | Ultra 20x (30 ТБ) 1 месяц бесплатно, затем $199.99/мес. |
| `yt_1m` | `g1.youtube_premium_individual_add_on` | `eft-1mo` | YouTube Premium (индивидуальный) 1 месяц бесплатно, затем $11.99/мес. |
| `yt_family` | `g1.youtube_premium_family_add_on` | `eft-1mo` | YouTube Premium (семейный) 1 месяц бесплатно |
| `yt_lite` | `g1.youtube_premium_lite_add_on` | `eft-1mo` | YouTube Premium Lite 1 месяц бесплатно |

Всего бесплатных подтверждённых записей: 30.

## Все уникальные SKU — одним списком, для копирования

```text
g1.100gb
g1.100gb.1month_eft
g1.100gb.3months_eft
g1.100gb.3months_ip_83p.acq
g1.100gb.3months_ip_85p.acq
g1.100gb.annual
g1.10tb
g1.10tb.1month_ip_90p
g1.10tb.3months_ip_85p
g1.10tb.annual
g1.200gb
g1.200gb.1month_eft
g1.200gb.3months_eft
g1.200gb.3months_ip_83p.acq
g1.200gb.3months_ip_85p.acq
g1.200gb.annual
g1.20tb
g1.20tb.12months_eft
g1.20tb.1month_eft
g1.20tb.3months_ip_75p.acq
g1.20tb.3months_ip_80p.acq
g1.20tb.3months_ip_90p.acq
g1.20tb.ai
g1.20tb.ai.subs_variant
g1.20tb.v2
g1.2tb
g1.2tb.12months_eft
g1.2tb.1month_eft
g1.2tb.3months_eft
g1.2tb.3months_ip_85p.acq
g1.2tb.6months_eft
g1.2tb.ai
g1.2tb.ai.3months_ip_75p.acq
g1.2tb.ai.annual
g1.2tb.ai.subs_variant
g1.2tb.annual
g1.2tb.subs_variant
g1.30gb
g1.30gb.1month_eft
g1.30gb.3months_ip_83p.acq
g1.30gb.3months_ip_85p.acq
g1.30gb.annual
g1.30tb
g1.30tb.12months_eft
g1.30tb.1month_eft
g1.30tb.ai
g1.30tb.ai.subs_variant
g1.5tb
g1.5tb.3months_ip_75p.acq
g1.5tb.ai
g1.5tb.ai.subs_variant
g1.5tb.annual
g1.ai
g1.ai.plus
g1.ai.pro
g1.ai.ultra
g1.ai.ultra.1month_ip_75p.acq
g1.ai.ultra.1month_ip_90p.acq
g1.ai.ultra.3months_ip_75p.acq
g1.ai.ultra.3months_ip_80p.acq
g1.ai.ultra.3months_ip_90p.acq
g1.health_premium
g1.helium
g1.helium.3months_ip_75p.acq
g1.helium.3months_ip_83p.acq
g1.home_premium
g1.play
g1.play.20tb
g1.play.20tb.12month
g1.play.2tb
g1.play.2tb.ai
g1.play.30tb
g1.play.30tb.12month
g1.play.5tb
g1.play.5tb.12month
g1.play.ai
g1.play.ai.plus
g1.play.ai.pro
g1.play.ai.pro.12month
g1.play.ai.ultra
g1.play.health
g1.play.helium
g1.play.home
g1.play.plus
g1.play.pro
g1.plus
g1.premium
g1.pro
g1.ultra
g1.ultra.20tb
g1.ultra.30tb
g1.youtube_premium_family_add_on
g1.youtube_premium_individual_add_on
g1.youtube_premium_lite_add_on
```

## Все записи SKU + offer — для копирования

```text
g1.30gb  
g1.30gb.annual  
g1.30gb.1month_eft  eft-1month
g1.30gb.3months_ip_85p.acq  introprice
g1.100gb  
g1.100gb.annual  
g1.100gb.1month_eft  freetrial
g1.100gb.3months_eft  freetrial
g1.100gb.3months_ip_85p.acq  introprice
g1.200gb  
g1.200gb.annual  
g1.200gb.1month_eft  freetrial
g1.200gb.3months_eft  freetrial
g1.200gb.3months_ip_85p.acq  introprice
g1.helium  
g1.play.helium  eft-12mo
g1.play.helium  eft-6mo
g1.play.helium  eft-3mo
g1.play.helium  eft-1mo
g1.helium.3months_ip_75p.acq  introprice
g1.2tb  
g1.2tb.annual  
g1.2tb.1month_eft  freetrial
g1.2tb.3months_eft  freetrial
g1.2tb.6months_eft  freetrial
g1.2tb.subs_variant  6months-eft
g1.2tb.subs_variant  3months-eft
g1.2tb.3months_ip_85p.acq  introprice
g1.2tb.ai  
g1.2tb.ai.annual  
g1.5tb  
g1.5tb.annual  
g1.2tb.ai.subs_variant  12months-eft
g1.2tb.ai.subs_variant  6months-eft
g1.2tb.ai.subs_variant  6months-eft-2
g1.2tb.ai.subs_variant  6months-eft-ss-2026
g1.play.2tb.ai  eft-3mo
g1.2tb.ai.3months_ip_75p.acq  introprice
g1.10tb  
g1.10tb.annual  
g1.10tb.1month_ip_90p  introprice
g1.10tb.3months_ip_85p  introprice
g1.20tb  
g1.20tb.v2  
g1.play.20tb  
g1.play.20tb  eft-12month
g1.play.20tb  eft-6month
g1.play.20tb  eft-3month
g1.play.20tb  eft-1month
g1.20tb.3months_ip_90p.acq  introprice
g1.20tb.3months_ip_80p.acq  introprice
g1.20tb.3months_ip_75p.acq  introprice
g1.30tb  
g1.ai.pro  
g1.play.ai.pro  
g1.play.ai.pro  eft-12mo
g1.play.ai.pro  eft-6mo
g1.play.ai.pro  eft-3mo
g1.play.ai.pro  eft-1mo
g1.ai.ultra.1month_ip_90p.acq  introprice
g1.ai.ultra.3months_ip_90p.acq  introprice
g1.ai.ultra.3months_ip_80p.acq  introprice
g1.ai.ultra.1month_ip_75p.acq  introprice
g1.ai.ultra.3months_ip_75p.acq  introprice
g1.youtube_premium_individual_add_on  eft-1mo
g1.youtube_premium_family_add_on  eft-1mo
g1.youtube_premium_lite_add_on  eft-1mo
g1.2tb.12months_eft  freetrial
g1.20tb.1month_eft  freetrial
g1.20tb.12months_eft  freetrial
g1.30tb.1month_eft  freetrial
g1.30tb.12months_eft  freetrial
g1.ai  
g1.ai.plus  
g1.ai.ultra  
g1.5tb.ai  
g1.20tb.ai  
g1.30tb.ai  
g1.5tb.ai.subs_variant  
g1.20tb.ai.subs_variant  
g1.30tb.ai.subs_variant  
g1.play  
g1.play.ai  
g1.play.2tb  
g1.play.5tb  
g1.play.30tb  
g1.play.ai.plus  
g1.play.ai.ultra  
g1.play.pro  
g1.play.plus  
g1.play.20tb.12month  
g1.play.ai.pro.12month  
g1.play.30tb.12month  
g1.play.5tb.12month  
g1.5tb.3months_ip_75p.acq  introprice
g1.100gb.3months_ip_83p.acq  introprice
g1.200gb.3months_ip_83p.acq  introprice
g1.30gb.3months_ip_83p.acq  introprice
g1.helium.3months_ip_83p.acq  introprice
g1.home_premium  
g1.health_premium  
g1.play.home  
g1.play.health  
g1.ultra  
g1.ultra.20tb  
g1.ultra.30tb  
g1.pro  
g1.plus  
g1.premium  
```

## Проверка

```bash
node --check frida.js
python main.py --plan helium_1m   # проверка окружения, без покупки
```

Живой ответ Play — единственный критерий: `n>0` — код живой, `no_offer` — нет.
