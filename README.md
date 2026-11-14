# HGH 萧山个人拍机助手 (HGH Plane Spotter)

面向个人拍机场景的轻量级雷达与数据记录工具，针对**杭州萧山国际机场（HGH / ZSHC）**定制，同时支持**彩绘客机**与**货机**。

---

## ⚡ 常用控制：怎么开 / 怎么关（macOS 原生后台）

### 1. 开启后台常驻（关掉终端也一直跑，开机自启）
```bash
cd ~/Desktop/hgh-plane-spotter
./scripts/install_launchd.sh
```
- 本机浏览器访问：`http://127.0.0.1:8787`
- 手机 Tailscale 访问：`http://<Mac的Tailscale虚拟IP>:8787`

### 2. 彻底关闭服务（立即停止 + 取消开机自启）
```bash
cd ~/Desktop/hgh-plane-spotter
./scripts/uninstall_launchd.sh
```
> 不会删除代码和历史数据库 `hgh_spotter.db`，下次想开时再运行 `install_launchd.sh` 即可。

### 3. 查看运行状态与日志
```bash
# 查看是否在后台运行（有输出表示运行中，无输出表示已关闭）
launchctl list | grep planespotter

# 查看实时运行日志
tail -f ~/Desktop/hgh-plane-spotter/logs/stderr.log
```

---

## 核心功能

- **多源并发全量雷达（10 秒刷新）+ AirLabs 手动补盲**：平时并发拉取 `adsb.lol`、`airplanes.live`、`adsb.one`、`adsb.fi` 四个开源 ADS-B 数据源（零额度消耗）；出门拍机发现低空或近场漏抓时，可点击「AirLabs补盲」（每次仅消耗 1 次 AirLabs 额度）一次性拉回 HGH 周边商业级实时飞机位置、注册号与机型。
- **HGH 实时天气与跑道风向建议（METAR）**：自动拉取 `ZSHC` 实时 METAR 气象报文，展示风向、风速、气温、能见度，并根据逆风起降原则直接给出建议蹲守跑道方向（`06/07` 或 `24/25`）。
- **可折叠 HGH 雷达地图**：支持一键展开/收起轻量级暗色雷达地图，直观绘制萧山机场 `06/24` 与 `07/25` 两条跑道及五边延长线，并实时标注空中飞机位置。
- **三维度自由组合筛选**：支持同时按 **机型类型**（`全部` / `宽体机` / `窄体机` / `货机`）、**涂装属性**（`全部` / `仅彩绘` / `非彩绘`）与 **进出港流向**（`全部` / `进港` / `出港` / `过境`）筛选。
- **HGH 今日进出港时刻表（可选）**：支持接入 **AirLabs 免费 API Key**，自动分页拉取 HGH 当日进港与出港排班（默认每次最多翻 4 页、每 8 小时同步一次以节省免费额度），自动合并代码共享重复班次，提供 **「计划 / 预计 / 实际」×「起飞 / 落地」** 组合时间排序与高亮展示。
- **HGH 跑道自动识别与记录**：基于萧山机场 `06/24` 与 `07/25` 两条平行跑道几何参数，自动判定所有进港飞机的历史降落跑道号并标记白天/夜间时段。
- **航线规律预测（支持 `HGH` / `非HGH` 切换）**：结合 `adsbdb.com`、`hexdb.io` 与本地历史起降日志，按近 14 天星期与时段频次辅助预判串飞规律，顶部支持一键切换只看 `HGH`、`非HGH` 或 `全部` 航线。
- **可选手机锁屏推送**：支持 Bark（iOS）或通用 Webhook（如 Server酱 / PushPlus），目标飞机飞往或接近 HGH 时自动推送提醒。

## 本地运行（macOS + Tailscale 方案）

### 1. 临时前台调试运行（可选）
如果不想装成后台服务，只是临时调试看效果，可以直接执行 `./start.sh`（关闭终端窗口即停止）。如需自定义端口可先执行 `export PORT=你的端口`。

### 2. 出门只带手机如何访问？（Tailscale）
1. 在家里的 Mac 和随身手机上分别安装 **Tailscale** 并登录同一个账号。
2. 在 Mac 终端或 Tailscale 状态栏查看本机的虚拟内网 IP（通常为 `100.x.x.x`）。
3. 出门在外开启手机 Tailscale 后，手机浏览器直接访问：`http://100.x.x.x:8787`（建议添加到手机主屏幕）。
4. 保持家里 Mac 插电且关闭系统休眠即可持续挂机记录历史航线与跑道。

### 3. 批量添加你关注的彩绘机 / 货机注册号
除了在网页端「关注清单」直接输入注册号添加外，也可以在终端用脚本批量查询 Hex 并同步：
```bash
source .venv/bin/activate
python scripts/sync_watchlist.py B-2021 B-2001 B-2476
```

### 4. 配置手机推送（可选）
启动前设置环境变量即可：
```bash
export BARK_URL="https://api.day.app/你的BarkKey"
./start.sh
```

## 云端部署（可选）
项目内置 `Dockerfile`，如需迁移到 1 核 1G 轻量云主机，直接构建运行即可：
```bash
docker build -t hgh-spotter .
docker run -d -p 8787:8787 -v $(pwd)/data:/app/data -e HGH_DB_PATH=/app/data/hgh_spotter.db hgh-spotter
```

## 注意事项
- 开源 ADS-B 网络在部分区域可能存在低空信号盲区，若落地前高于 3000 ft 丢失信号，跑道记录会自动降级记录为大方向（`06/07方向` 或 `24/25方向`）。
