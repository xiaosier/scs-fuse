# scs-fuse
将新浪云存储的资源通过fuse挂载到本地的文件夹中

# 安装
yum install fuse.x86_64 fuse-devel.x86_64

pip install fuse-python scs-sdk

修改 online.py中的
```
scs_accesskey = '你的新浪云存储ak'
scs_secretkey = '你的新浪云存储sk'
scs_bucket = '你的bucket名'
```

# 启动/重启

chmod +x opr.sh && mkdir -p /data2/ && ./opr.sh

# 测试
ls /data2/ && echo "hello" > /data2/hello.txt
