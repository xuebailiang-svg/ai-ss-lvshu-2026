# 系统配置中心

系统配置中心用于管理后端第三方服务配置。API Key 使用 Fernet 加密后保存到
`system_configs`，运行时优先读取数据库；数据库没有对应配置时回退环境变量。

服务器仍需一次性配置两个安全变量：

```env
SYSTEM_CONFIG_ENCRYPTION_KEY=至少32位随机字符串
ADMIN_CONFIG_TOKEN=独立的管理员强密码
```

这两个值不能通过 Web 修改，也不能保存到数据库。修改加密主密钥会导致已有密文无法解密。

公开状态接口不会返回完整 Key。写入和连接测试接口必须通过请求头：

```http
X-Admin-Token: <ADMIN_CONFIG_TOKEN>
```

当前支持：

- `deepseek_api_key`
- `deepseek_base_url`
- `deepseek_model`
- `amap_web_service_key`

表结构和服务均可继续扩展其他第三方配置，但必须为新增敏感字段配置加密与脱敏策略。
