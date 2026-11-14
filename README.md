# HGH 萧山个人拍机助手 (HGH Plane Spotter)

面向个人拍机场景的轻量级雷达与数据记录工具，针对**杭州萧山国际机场（HGH / ZSHC）**定制，同时支持**彩绘客机**与**货机**。

## 核心功能

- **HGH 周边实时雷达**：每 30 秒拉取 `adsb.lol` 开源数据，关注清单中的彩绘机与货机自动高亮置顶，展示距离、高度、升降趋势、航线与估算 ETA。
- **HGH 跑道自动识别与记录**：基于萧山机场 `06/24` 与 `07/25` 两条平行跑道几何参数，自动判定历史降落跑道号并标记白天/夜间时段。
- **航线与 1~2 天规律预测**：结合 `hexdb.io` 呼号反查与本地历史起降日志，按近 14 天星期与时段频次辅助预判串飞规律。
- **可选手机锁屏推送**：支持 Bark（iOS）或通用 Webhook（如 Server酱 / PushPlus），目标飞机飞往或接近 HGH 时自动推送提醒。

## 本地运行（macOS + Tailscale 方案）

### 1. 启动与关闭（macOS 后台自启 `launchd` 方案，最省资源）
安装并开启后台常驻（关掉终端也能一直运行，开机自动启动）：
```bash
cd ~/Desktop/hgh-plane-spotter
./scripts/install_launchd.sh
```
彻底停止并关闭后台服务（同时取消开机自启）：
```bash
cd ~/Desktop/hgh-plane-spotter
./scripts/uninstall_launchd.sh
```
如果只是临时在前台调试运行，也可以直接执行 `./start.sh`。
启动后本机浏览器访问：`http://127.0.0.1:8787`（如需自定义端口可先执行 `export PORT=你的端口`）

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
