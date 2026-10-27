# OpenWrt 25.12 自编译固件 — 京东云 AX1800 Pro（RE-SS-01）

为 **京东云 AX1800 Pro（代号"亚瑟"，型号 RE-SS-01）** 构建的 OpenWrt 固件，基于官方稳定分支 `openwrt-25.12`，由 GitHub Actions 云端编译，无 WiFi、带 OpenClash 与简体中文界面。

> 仓库名里的 `re-cs-02` 是早期命名遗留，实际适配机型是 **RE-SS-01**（`jdcloud,re-ss-01`）。

---

## 一、快速开始

### 已编译好的固件

在 [Actions 页面](../../actions) 选最新的成功运行，下载 Artifact 中的：

```
openwrt-25.12-jdcloud-re-ss-01-factory-kernel6M.bin
```

### 刷机步骤（U-Boot Web 不死）

1. **备份**：先备份 eMMC 分区表和 U-Boot（见下方"注意事项"第 1 条）。
2. 路由器断电 → 按住 `reset` → 上电 → 约 10 秒后松开。
3. **关闭电脑的 WiFi**（家用主路由多半也是 `192.168.1.1`，会抢默认路由）。
4. 电脑有线网卡设为静态 `192.168.1.2` / `255.255.255.0`，网关与 DNS 留空。
5. 浏览器打开 `http://192.168.1.1`，上传上一步的 `.bin`，等待写入完成并自动重启。
6. 重启后把网卡改回自动获取，**网线必须插 LAN 口**（见"注意事项"第 2 条）。

### 刷完后立即做

- 设置 root 密码（LuCI → 系统 → 管理权，或 SSH 执行 `passwd`）。**固件默认无密码。**
- 配置 WAN（PPPoE 或 DHCP）。
- 可选：把 56GB 的空闲分区做成 extroot，把根分区从 37M 扩到约 52G（见"注意事项"第 4 条）。

---

## 二、固件内容

| 类别 | 内容 |
|---|---|
| 基础 | OpenWrt 25.12-SNAPSHOT，Linux 6.12，LuCI + 简体中文 |
| 代理 | OpenClash（随固件编译，nftables / Firewall4 模式） |
| 依赖 | bash、curl、ca-bundle、ip-full、ruby、ruby-yaml、unzip、dnsmasq-full |
| 内核模块 | kmod-tun、kmod-nft-tproxy、kmod-inet-diag |
| 工具 | htop |
| 不含 | **全部 WiFi 相关包**（ath11k 驱动、固件、hostapd/wpad 均已关闭） |

内核配置为 `CONFIG_TARGET_ROOTFS_INITRAMFS=y`，同时产出内存启动镜像用于救急。

---

## 三、硬件规格（实机实测，非厂商标称）

| 项目 | 实测值 | 备注 |
|---|---|---|
| SoC | Qualcomm IPQ6000（ipq60xx 子目标） | Cortex-A53 四核 |
| 内存 | **418 MB**（`MemTotal 418248 kB`） | 厂商标称 512MB，部分被预留 |
| eMMC | **约 57 GiB**（`59891712` 个 1K 块） | 厂商标称 64GB |
| 千兆口 | `lan1` `lan2` `lan3` + `wan` | 由 qca8075 外置 PHY 提供 |
| 2.5G 口 | **不可用** | 设备树中 `dp1` 为 `disabled` |
| 无线 | 未启用 | 本固件无 WiFi；无线由独立 AP 承担 |
| USB | 1 × USB3（`usb@8af8800`） | 可接存储做轻量共享/下载 |
| PCIe | 不可用 | 设备树中为 `disabled` |

### eMMC 分区布局

| 分区 | 大小 | 说明 |
|---|---|---|
| `0:HLOS` / `0:HLOS_1` | 6 MB ×2 | 内核，A/B 双槽 |
| `rootfs` / `rootfs_1` | 60 MB ×2 | 根文件系统，A/B 双槽 |
| `rootfs_data` | 20 MB | GPT 中有定义，但本固件未使用 |
| `storage` | 约 56 GB | 默认空置，可挂载或用作 extroot |

---

## 四、仓库结构

```
.
├── config.seed                 固件配置（包选择、WiFi 关闭、initramfs 开关）
├── patch/
│   ├── ipq6000-re-ss-01.dts    设备树（网口划分、ESS 交换机、PHY）
│   ├── device.mk               镜像定义（FitImage + EmmcImage，内核 6MB）
│   ├── inject.py               往 ipq60xx 板级脚本注入本机型号（锚点注入）
│   ├── mkfactory.py            由 sysupgrade 包合成 U-Boot 可刷的 factory 镜像
│   └── i18n/*.lmo              LuCI 简体中文翻译文件
└── .github/workflows/
    ├── build-2512.yml          当前使用：openwrt-25.12 稳定分支
    └── build.yml               早期版本：master 分支（保留备查）
```

### 补丁机制说明

`patch/inject.py` 采用**锚点注入**而非整文件替换：把 `jdcloud,re-ss-01` 写入
`target/linux/qualcommax/ipq60xx/` 下的两个板级脚本 ——

- `base-files/etc/board.d/02_network`：划分 `lan1 lan2 lan3` 与 `wan`
- `base-files/lib/upgrade/platform.sh`：**显式拒绝系统内 sysupgrade**

锚点一旦失配会立即报错终止，不会静默产出错误固件。

关于中文：`config.seed` 里的 `CONFIG_PACKAGE_luci-i18n-*-zh-cn` 会在 `make defconfig`
阶段被丢弃（实测产物不含任何 i18n 包），因此改用 buildroot 顶层 `files/` 机制把
`.lmo` 直接铺进根文件系统，确保中文随镜像下发。

---

## 五、编译产物

| 文件 | 用途 |
|---|---|
| `*-factory-kernel6M.bin` | **主用**：内核 6MB + rootfs，U-Boot Web 不死直接刷入 |
| `*-squashfs-sysupgrade.bin` | sysupgrade 包（本设备已禁用系统内升级，主要用于提取 kernel/root） |
| `*-initramfs-uImage.itb` | 内存启动镜像，U-Boot 上传后从 RAM 启动，不写盘，用于救急与验证 |
| `*-squashfs-factory.bin` | `EmmcImage` 产生的纯 rootfs（不含内核），**不能**直接用于 Web 刷机 |

`factory-kernel6M.bin` 的布局与 U-Boot 的类型识别严格对应：

```
0x000000    FIT（kernel + fdt）      魔数 d00dfeed
0x600000    squashfs rootfs          魔数 hsqs
...         0x00 填充至 24 MiB       用于刷机时抹掉残留的旧 overlay
```

---

## 六、自己编译

1. Fork 本仓库。
2. Actions → 选择 **Build OpenWrt 25.12 stable (JDCloud RE-SS-01, no WiFi)** → Run workflow。
3. 参数 `no_wifi` 保持 `true`（关闭 WiFi）。
4. 编译约 **60 分钟**，完成后在 run 页面下载 Artifact（保留 30 天）。

工作流内置三道保险：

- **Rust 熔断**：25.12 分支的 ruby 在 aarch64 上默认开启 YJIT，会通过 `RUBY_ENABLE_YJIT:rust/host`
  拉起整套 Rust 工具链（2~4 小时）。配置校验阶段检测到即中止。
- **看门狗**：日志 25 分钟无增长且 CPU 空闲才判定卡死并重试（避免误判正常的大段静默编译）。
- **产物保护**：上传步骤使用 `!cancelled()`，后处理失败也能取回原始镜像。

---

## 七、注意事项与已知坑

### 1. 刷机前先备份

U-Boot 的 Web 不死入口（按住 reset 上电）始终可用，是最终的恢复手段。
但仍建议在动手前备份分区表与 U-Boot：

```bash
# 在系统内执行
dd if=/dev/mmcblk0 of=/tmp/gpt-backup.img bs=512 count=34
dd if=/dev/mmcblk0p13 of=/tmp/uboot-backup.bin
```

### 2. 只有 LAN 口能拿到 IP

这是最常见的"刷完上不了网"原因。设备树里只有 `lan1`/`lan2`/`lan3` 加入 `br-lan` 并运行 DHCP；
`wan` 口是 DHCP 客户端，`dp1`（2.5G）在设备树中未启用。网线插错口不会有任何地址分配。

### 3. 系统内 sysupgrade 已被故意禁用

该机为 eMMC 启动，`platform.sh` 中的 `nand_do_upgrade`（UBI 专用）和 `default_do_upgrade`
（内部调用 `mtd write`）都不适用。因此补丁里显式拒绝并提示改用 U-Boot Web 刷机，避免写坏分区。

### 4. overlay 的位置与扩容

系统默认把 overlay 建在 **rootfs 分区内、rootfs 镜像之后**的 loop 设备上（约 37 MB），
**不是** GPT 里的 `rootfs_data` 分区。因此每次刷机都会连同旧配置一起清掉。

想扩容可把空闲的 `storage` 分区做成 extroot（约 52 GB）。注意刷机后该配置会随 overlay 一起丢失，需要重新配置。

### 5. U-Boot 的 `mmc` 命令参数是十六进制

在 U-Boot 命令行里，`mmc read/erase` 的地址与块数按十六进制解析。
直接用十进制写会操作到错误的分区。尽量使用按分区名操作的 `flasherase <name>`。

### 6. 刷新固件等于恢复出厂

factory 镜像刷入会清空 overlay，所有配置（PPPoE 账号、密码、插件设置）都会丢失。
刷之前请先确认宽带账号密码。
