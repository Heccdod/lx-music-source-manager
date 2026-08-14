# LX Music 音源一键导入 / 更新工具

针对 [lx-music-desktop](https://github.com/lyswhut/lx-music-desktop)（洛雪音乐桌面版）的自定义音源批量管理工具，带图形界面，一站式完成音源的导入、更新、备份、还原与清除。

> 本工具只是一个管理工具，不内置、不提供任何音源脚本。
> 自用，使用Deepseek辅助开发

## 功能

- 自动定位 user_api.json（找不到可手动重新定位）
- 选择文件夹后递归识别所有 .js 音源，并解析脚本头部的 @name / @version / @description / @author / @homepage 元数据
- 待导入列表：点击整行勾选、全选、搜索过滤、移除（仅移出名单，不删除磁盘文件）
- 两种导入模式：
  - 导入模式：直接新增（内容完全相同自动跳过）
  - 更新模式：按音源名称自动匹配，同名覆盖更新（保留 id），无同名则新增
- 一键全部导入 / 更新
- 已导入音源查看（名称 / 版本 / 作者 / 描述 + 详情预览），删除所选、一键清除
- 备份管理：手动备份、一键还原、查看 / 删除 / 清空；所有写操作前自动备份
- GitHub 订阅更新：添加仓库订阅，一键检查并下载最新 Release 音源，自动以更新模式导入
  - 单击订阅：把该订阅已下载的音源加载进「待导入音源」列表
  - 双击订阅：立即下载并更新该订阅
  - 下载自动解压到 下载目录/<仓库名>/ 子文件夹（zip 附件自动解压）
  - 支持镜像前缀加速（内置常用镜像预设，国内网络友好）
  - 检测到 IDM（Internet Download Manager）时自动调起 IDM 下载，也可切换内置下载
  - 可选保存历史订阅：更新前把旧版本归档到 history 子目录（默认关闭）
- 设置页（标题栏设置按钮）：
  - 备份配置：自动备份开关（关闭后隐藏备份模块）、备份文件夹自定义（支持旧备份迁移）
  - 订阅配置：下载目录自定义、IDM 开关、历史订阅开关、已有订阅管理（打开文件夹 / 删除）
  - 日志配置：记录日志（写入 config/logs/app.log）、日志窗口显示（需先开启记录日志）
- 配置集中存放：所有配置/日志/备份都在程序目录的 config 文件夹内，不散落
- 界面优先使用 customtkinter，安装失败自动回退内置 ttk 界面

## 界面预览

![界面预览](exe.png)

<!-- ![界面预览](screenshot.png) -->

## 使用

方式一：运行源码

    pip install customtkinter
    python LXmusic一键导入和更新.py

方式二：打包为独立 exe

    pip install pyinstaller
    pyinstaller --onefile --windowed --name "LXmusic一键导入和更新" LXmusic一键导入和更新.py

生成结果在 dist 目录。

## 目录结构

    <程序目录>/
    ├── LXmusic一键导入和更新.py / .exe
    └── config/                # 全部配置集中存放
        ├── settings.json      # 应用设置（镜像、IDM、备份、日志、下载目录…）
        ├── subscriptions.json # 订阅列表
        ├── backups/           # 备份文件（可在设置中修改位置）
        └── logs/app.log       # 运行日志

## 注意事项

- 修改 user_api.json 后需重启 LX Music 桌面版才会生效。
- 脚本以官方格式（gz_ + zlib + base64）压缩存储。
- 操作无需管理员权限。
- 订阅下载的脚本会被 LX Music 直接执行，请只订阅可信仓库。

## 免责声明

本项目仅用于学习与技术交流，是一个文件管理工具，不内置、不提供、不附带任何音乐源脚本。请遵守相关法律法规与各音源脚本作者的使用条款，由此产生的一切后果由使用者自行承担。本项目与 lx-music-desktop / 洛雪官方无任何关联。

## 致谢

- [lx-music-desktop](https://github.com/lyswhut/lx-music-desktop) —— 自定义音源的数据格式与机制

## License

[MIT](LICENSE)
