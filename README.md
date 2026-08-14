# LX Music 音源一键导入 / 更新工具

针对 [lx-music-desktop](https://github.com/lyswhut/lx-music-desktop)（洛雪音乐桌面版）的自定义音源批量管理工具，带图形界面，一站式完成音源的导入、更新、备份、还原与清除。

> 本工具只做「管理」，不内置、不提供任何音源脚本。

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
- 界面优先使用 customtkinter，安装失败自动回退内置 ttk 界面

## 界面预览

（运行后截一张图，放到仓库里，再把下面这行的注释去掉即可显示）

<!-- ![界面预览](screenshot.png) -->

## 使用

方式一：运行源码

    pip install customtkinter
    python LXmusic一键导入和更新.py

方式二：打包为独立 exe

    pip install pyinstaller
    pyinstaller --onefile --windowed --name "LXmusic一键导入和更新" LXmusic一键导入和更新.py

生成结果在 dist 目录。

## 注意事项

- 修改 user_api.json 后需重启 LX Music 桌面版才会生效。
- 脚本以官方格式（gz_ + zlib + base64）压缩存储。
- 操作无需管理员权限。

## 免责声明

本项目仅用于学习与技术交流，是一个文件管理工具，不内置、不提供、不附带任何音乐源脚本。请遵守相关法律法规与各音源脚本作者的使用条款，由此产生的一切后果由使用者自行承担。本项目与 lx-music-desktop / 洛雪官方无任何关联。

## 致谢

- [lx-music-desktop](https://github.com/lyswhut/lx-music-desktop) —— 自定义音源的数据格式与机制

## License

[MIT](LICENSE)
