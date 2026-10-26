# OpenWrt 自编译固件 — 京东云 AX1800 Pro（RE-CS-02 / AP-CP03-C1）

基于 **OpenWrt 主线 master** 源码，通过 GitHub Actions 云端编译。

## 固件内容（精简定制）

- **OpenClash**（luci-app-openclash，随固件编译，nftables/Firewall4 模式）
- LuCI 简体中文界面
- OpenClash 全套依赖：bash / dnsmasq-full / curl / ip-full / ruby / kmod-tun / kmod-nft-tproxy 等
- htop
- 不含任何多余插件

## 设备规格

| 项目 | 参数 |
|---|---|
| SoC | Qualcomm IPQ6010 (Cortex-A53 @ 1.8GHz) |
| 内存 | 1 GiB |
| 闪存 | 128/256 GB eMMC |
| 网口 | 4x 1Gbps + 1x 2.5Gbps |
| 无线 | QCN5022 (2.4G AX 2x2) + QCN5052 (5.8G AX 2x2) + QCN9024 (5.2G AX 4x4) |

## 编译产物

| 文件 | 用途 |
|---|---|
| `*-initramfs-uImage.itb` | **过渡启动镜像**（TFTP/U-Boot 启动用，不写盘） |
| `*-sysupgrade.bin` | 正式系统镜像（initramfs 启动成功后写入） |

## 使用方法

1. Fork/使用本仓库 → Actions 页手动触发 `Build OpenWrt (JDCloud RE-CS-02)`
2. 编译约 2-4 小时，完成后在 run 页面 Artifacts 下载固件
3. 刷机：先经 U-Boot/initramfs 过渡（**从 QWRT/原厂不能直接 sysupgrade，会变砖**）

## 刷机警告

⚠️ 从京东云原厂固件或 QWRT 切换到本固件，分区布局不同，**禁止直接 sysupgrade**。
正确路径：确认/刷入支持主线镜像的 U-Boot → initramfs 启动 → sysupgrade 写入。
动手前务必先备份 U-Boot 与关键分区。
