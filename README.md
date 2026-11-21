# Google One 套餐注入器

在已 root 的 Android 设备上注入 Google One，按套餐弹出 Play 收银台。  
**不会自动点订阅**，确认页留给你自己点。

你只需要准备：**Root + 已登录 Google + 已安装 Google One**。  
`frida-server`、`module_521.apk`、adb 连接由 `main.py` 自动补齐。

## 运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

```text
python main.py --plan helium_1m          # 直接新购
python main.py --renew --plan pro_6m     # 续费叠加
python main.py --serial emulator-5560    # 指定设备（一般不用）
```

## 菜单

套餐按 **Plus / Pro / Ultra 5x / Ultra 20x** 分组，列表来自 `frida.js` 的 `PLANS`。

| 输入 | 作用 |
|------|------|
| 编号或套餐名 | 下单，弹出收银台 |
| `s` | 切换续费叠加（`STACK`） |
| `a` | 附加 YouTube 套餐 |
| `e` | 再跑一遍环境检测 |
| `g` | 重启 Google One 并重新注入 |
| `q` | 退出 |

## 新购和续费

`frida.js`：

```js
var STACK = false; // 新购
var STACK = true;  // 续费：叠到现有 Google One 订阅上（ReplacementMode = 5）
```

默认新购。菜单按 `s`，或命令行加 `--renew`。续费要求当前账号已经有一笔可叠加的订阅。

## 脚本会自动做的事

1. 查找 adb（PATH / Android SDK / MuMu 安装目录）
2. 没有设备时重启 adb，并尝试连接 MuMu / 雷电 / 夜神常用端口
3. 多设备去重，优先选已 root、已装 Google One、已登录的那台
4. 本机没有 Frida 则 `pip install frida-tools`
5. 缺少 `/data/local/tmp/module_521.apk` 时从 `module_b64.py` 解开并 push
6. 设备 `frida-server` 缺失或版本和本机不一致时，从 `assets/` 或 GitHub 补齐并启动

## 文件

| 文件 | 说明 |
|------|------|
| `main.py` | 入口：环境、菜单、注入 |
| `frida.js` | Frida 插件，含套餐表和 BillingClient 逻辑 |
| `module_b64.py` | BillingClient 5.2.1 dex |
| `requirements.txt` | Python 依赖 |
| `assets/` | 缓存的 `frida-server` |

设备路径：

- `/data/local/tmp/module_521.apk`
- `/data/local/tmp/frida-server`
