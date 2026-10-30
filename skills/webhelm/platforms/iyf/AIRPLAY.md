# IYF Safari → Roku AirPlay 操作手册

## 已验证环境（2026-10-11）
- Mac 上 Safari 播放爱壹帆视频，Roku 设备名：`43in MAGNAVOX Roku TV`。
- CLI：`skills/webhelm/platforms/iyf/safari-airplay`（相对于仓库根目录）。
- 《沙丘》播放地址：`https://www.iyf.tv/play/Ob1Hrzz7x7t`。
- 已执行 3 次 Safari 退出、重新打开《沙丘》、CLI 连接的冷启动测试，3/3 返回 `CONNECTED`；不代表长时间播放或《沙丘2》已验证。

## 新会话操作
1. 通过 NeoY 在 Mac 上执行 `open -a Safari 'https://www.iyf.tv/play/Ob1Hrzz7x7t'`（其他影片先找到其正确 URL）。
2. 确保 Safari 当前标签页中 HTML video 已开始播放；如需要，通过 Safari UI 操作播放。
3. 从仓库根目录执行 `zsh skills/webhelm/platforms/iyf/safari-airplay '43in MAGNAVOX Roku TV'`。
4. 必须确认输出 `CONNECTED: 43in MAGNAVOX Roku TV`，并查询 Safari 当前视频的 `webkitCurrentPlaybackTargetIsWireless`；必要时让用户确认电视实际画面。
5. 若失败，逐项检查 Safari 页面、视频播放状态、设备发现、macOS 辅助功能权限和 Roku AirPlay 设置。避免把屏幕镜像误当成视频直投。

## CLI 工作机制和限制
- 通过 Safari AppleScript `do JavaScript` 调用 HTMLVideoElement `webkitShowPlaybackTargetPicker()`，再由 System Events 选择 AirPlay 目标。
- 对失败最多尝试 5 次；以 `webkitCurrentPlaybackTargetIsWireless` 为成功判据。
- 依赖 Safari UI 辅助功能树；UI 改版、播放器变更可能导致失效。
- `platforms/iyf/manifest.yaml` 仍标记 experimental，AirPlay 尚未注册为平台 action。
- Safari JavaScript 自动化需已允许；若不允许，按实际权限提示处理。

## 后续测试
- 《沙丘2》影片 URL、冷启动多轮、断线重连、长时间播放均待验证。
- 测试时把退出 Safari、打开页面、调用 CLI 拆为独立命令；不要声称未执行的测试成功。
