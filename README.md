# iCourse Subscriber

自动监控复旦大学 iCourse 平台课程更新，对新课次视频进行语音转文字、AI 摘要，并通过邮件推送。部署在 GitHub Actions 上，每天定时运行，无需自建服务器。

## 工作流程

```
WebVPN 登录 → iCourse CAS 认证 → 检测新课次
    ↓
下载视频 → ffmpeg 管道解码 → silero VAD 分段 → SenseVoice 识别
    ↓
Qwen2.5-72B 生成 Markdown 摘要 → QQ SMTP 邮件推送
    ↓
SQLite 记录已处理课次（幂等，失败自动重试）
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 认证 | 逆向的复旦WebVPN AES-128-CFB + IDP CAS (RSA) |
| 语音转文字 | ffmpeg pipe + sherpa-onnx + SenseVoice-Small (int8) |
| 语音分段 | silero VAD |
| LLM 摘要 | ModelScope API (GLM-5) |
| 邮件 | QQ SMTP SSL (465) |
| 存储 | SQLite，AES-256-CBC 加密缓存 |
| 调度 | GitHub Actions cron |

## 部署

### 1. Fork 本仓库或推送到 GitHub

### 2. 配置 Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 说明 |
|--------|------|
| `STUID` | 复旦学号 |
| `UISPSW` | UIS 密码 |
| `COURSE_IDS` | 监控的课程 ID，逗号分隔（如 `35472,30251`） |
| `DASHSCOPE_API_KEY` | [ModelScope API Key](https://modelscope.cn/) |
| `SMTP_EMAIL` | QQ 邮箱地址 |
| `SMTP_PASSWORD` | QQ 邮箱 SMTP 授权码（非登录密码） |
| `RECEIVER_EMAIL` | 接收摘要的邮箱 |

### 3. 查找课程 ID

登录 iCourse 网页版，进入课程页面，URL 中的数字即为 `course_id`：

```
https://icourse.fudan.edu.cn/course/detail/35472
                                          ^^^^^
```

### 4. 运行

- **自动**：每天北京时间 22:00 自动执行
- **手动**：Actions → iCourse Check → Run workflow
- 可在 `.github/workflows/check.yml` 中修改 cron 表达式

## 数据安全

- **不保留音视频**：视频通过 ffmpeg 管道实时转录，转录完成立即删除
- **数据库加密**：SQLite 在 Actions 缓存前使用 `openssl aes-256-cbc` 加密，密钥由 `STUID + UISPSW + DASHSCOPE_API_KEY + SMTP_PASSWORD` 拼接派生
- **缓存优化**：ASR 模型（~200MB）和 pip 包均有独立缓存，首次运行后不再重复下载

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt
sudo apt install ffmpeg  # Linux

# 下载 ASR 模型
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
tar xf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx

# 设置环境变量（参考 .env.example）
export StuId=你的学号
export UISPsw=你的密码
export COURSE_IDS=35472
export DASHSCOPE_API_KEY=你的key
export SMTP_EMAIL=xxx@qq.com
export SMTP_PASSWORD=你的授权码
export RECEIVER_EMAIL=xxx@example.com

# 运行
python main.py
```

## 项目结构

```
├── main.py                 # 主流程编排
├── src/
│   ├── config.py           # 环境变量配置
│   ├── webvpn.py           # WebVPN 登录 + iCourse CAS 认证
│   ├── icourse.py          # iCourse API 客户端 + CDN 签名
│   ├── transcriber.py      # ffmpeg pipe + silero VAD + SenseVoice
│   ├── summarizer.py       # ModelScope LLM 摘要
│   ├── emailer.py          # QQ SMTP 邮件发送
│   └── database.py         # SQLite 存储
├── .github/workflows/
│   └── check.yml           # GitHub Actions 定时任务
├── requirements.txt
└── .env.example
```
