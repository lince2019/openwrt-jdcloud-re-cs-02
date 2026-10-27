define Device/jdcloud_re-ss-01
	$(call Device/FitImage)
	$(call Device/EmmcImage)
	DEVICE_VENDOR := JDCloud
	DEVICE_MODEL := RE-SS-01
	SOC := ipq6000
	BLOCKSIZE := 64k
	KERNEL_SIZE := 6144k
	DEVICE_DTS := ipq6000-re-ss-01
	DEVICE_DTS_CONFIG := config@cp03-c1
	SUPPORTED_DEVICES += jdcloud,re-ss-01
endef
TARGET_DEVICES += jdcloud_re-ss-01
