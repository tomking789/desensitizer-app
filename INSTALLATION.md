# 安装与发布说明

## 当前发布形式

当前专业试用版采用 Windows 便携安装包形式发布：

```text
本地资料脱敏工具-专业试用版-v073.zip
```

用户解压后双击：

```text
本地资料脱敏工具-release\本地资料脱敏工具.exe
```

## 为什么先采用便携安装包

便携安装包不写入注册表，不需要管理员权限，适合早期试点、企业内部分发和小范围验证。

正式商业发布时，建议进一步补齐：

- 安装向导
- 桌面快捷方式
- 开始菜单入口
- 卸载入口
- 代码签名证书
- 版本升级策略

这些可以使用 Inno Setup、NSIS 或 MSIX 完成。

## 输出目录

默认输出目录位于程序主目录下：

```text
本地资料脱敏工具-release\输出文件
```

这样用户更容易找到脱敏文件、报告和加密映射表。

## 发布包应包含

- `本地资料脱敏工具.exe`
- `_internal`
- `使用说明.txt`
- `README.md`
- `DISCLAIMER.md`
- `AGPL-3.0.txt`
- `LICENSE`
- `NOTICE.md`
- `SOURCE_CODE.md`
- `source-code.zip`
- `templates`
- `demo`
- `marketing`
- `enterprise`
