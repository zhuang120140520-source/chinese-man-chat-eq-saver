# Chinese Man 聊天情商拯救器

一个面向 Windows 微信单聊的 AI 回复助手，专注于认识异性、暧昧互动、邀约与恋爱相处。希望在你不知道怎么接话时，提供更贴近你们真实关系、更符合当前聊天目的的回复参考。

本项目基于 [jev-chat/jev-chat-windows](https://github.com/jev-chat/jev-chat-windows) 二次开发，判断内核沿用 Jev。感谢原项目作者和贡献者提供的开源代码与灵感，也感谢其上游项目 [jev-chat/jev-chat-jarvis](https://github.com/jev-chat/jev-chat-jarvis)。我们在原有聊天辅助能力的基础上，围绕异性相处与关系推进重新设计了人物资料、聊天目标、历史点评和记忆功能。

核心特点是：**先告诉 AI 你们是谁，再让它帮你接话。** 用户可以手动填写双方的背景、性格、喜好、共同经历和自己的表达风格，并设定本轮聊天目的，例如随便聊聊、增进感情、化解误会，或邀请对方一起参加活动。结合这些资料与聊天上下文，AI 尽量减少脱离实际情况的建议，让回复更贴近你的口吻，也更清楚你这次想达到什么效果。

主要功能：

- 按联系人保存人物档案，结合双方背景和共同经历生成建议。
- 随时切换聊天目的，在邀约等场景中给出具体的下一步建议。
- 补充以前的对话，由 AI 简要点评双方表现与整体交流。
- 点击按钮后才截图，通过本机 OCR 读取微信文字；首次可选择本轮起点。
- 查看、删除近期聊天与长期记忆，将聊天中的约定整理成待办。
- 提供候选回复、对话参考和紧张度评分，复制或填入后由用户确认发送。

当前仅支持 Windows，软件界面为简体中文。人物档案、长期记忆和待办在本机加密保存；生成建议时，相关文字会发送至用户配置的云端模型服务商。模型费用与数据留存取决于所选服务商。详见 [PRIVACY.md](PRIVACY.md)。

本项目为独立修改版，与上游作者及模型服务商无隶属关系。上游许可、署名及第三方组件说明见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。

---

# Chinese Man Chat EQ Saver

An AI reply assistant for one-to-one WeChat conversations on Windows, focused on meeting potential partners, flirting, planning dates, and communicating in a relationship. When you are unsure how to respond, it offers suggestions tailored to your relationship and the purpose of the conversation.

This project is derived from [jev-chat/jev-chat-windows](https://github.com/jev-chat/jev-chat-windows) and retains Jev as its decision engine. We thank the original authors and contributors for their open-source work and inspiration, as well as the upstream project [jev-chat/jev-chat-jarvis](https://github.com/jev-chat/jev-chat-jarvis). Building on the original chat assistant, we redesigned the profiles, conversation goals, historical reviews, and memory features for dating and relationship communication.

The central idea is: **tell the AI who you both are before asking it what to say.** Users can provide backgrounds, personalities, preferences, shared experiences, and their own speaking style. They can also set a goal for the current conversation, such as casual chatting, building a closer connection, resolving a misunderstanding, or inviting someone to an activity. With this information and the conversation context, the assistant aims to offer more grounded suggestions that reflect your voice and what you want to accomplish.

Key features:

- Contact-specific profiles that inform suggestions with personal context and shared experiences.
- Switchable conversation goals and concrete next-step suggestions for situations such as planning a date.
- Imported historical conversations with brief AI reviews of both participants and the overall exchange.
- Screenshots taken only when requested, with local OCR and a selectable starting message on the first capture.
- Viewable and removable recent context and long-term memories, plus a to-do list for arrangements discussed in chat.
- Reply candidates, conversation guidance, and a tension score; users review and send every message themselves.

Currently available for Windows with a Simplified Chinese interface. Profiles, long-term memories, and to-dos are encrypted locally. When generating suggestions, relevant text is sent to the cloud model providers configured by the user. Model costs and data retention depend on the selected providers. See [PRIVACY.md](PRIVACY.md).

This is an independent derivative project and is not affiliated with the upstream authors or model providers. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for attribution, licensing, and third-party component information.


## 开始使用

1. 双击 `jev-partner-chat.exe`，保留完整文件夹和 `_internal`，无需 Terminal。可通过右键菜单创建桌面快捷方式；开发者也可运行 `tools/create_desktop_shortcut.ps1 -Executable <exe完整路径>`。源码启动需在源码目录执行 `.\.venv\Scripts\python.exe main.py`，并先安装依赖。
2. 首次设置只有简体中文和模型配置。填写判断模型（如 TypeSafe / Jev）和起草模型（如 DeepSeek）的 API Key、来源与模型名，点「保存模型并返回聊天」。它是模型配置页，不是本软件的注册页；已配置的 Windows 用户密钥会沿用。不显示公众号横幅或重复的全局回复偏好。
3. 点「准备资料 · 人物档案与补充历史」。在第一栏「对方与关系」填写微信聊天窗口顶部显示的名称（包括备注，完全一致），再填双方资料、相处经历与表达风格。档案称呼可以不同；真正绑定的是微信聊天名。
4. 可在「补充历史」粘贴以前的聊天或导入 TXT，格式如下。点「AI 点评双方与对话」分别查看你、对方与整个对话的简评，附原文依据。这里不生成回复。

```text
我：上次那个展还挺有意思
她：下次有新展也叫我
```

5. 在「这轮目标」选择聊天目的，按需允许点击后整理记忆与待办，然后点「保存并返回聊天」。也有「保存档案」与「返回聊天」两个独立按钮；单独返回会保留未保存的草稿，下次打开可以继续编辑。
6. 软件启动、打开档案和切换联系人时不截图、不读取聊天。让最新消息显示在微信中，点首页「当前对话目的」下方绿色的「对方已说完 生成回复」，取得一张新画面并在本机 OCR。
7. 每位联系人本次打开软件的首次截图，会先显示「选择本轮聊天起点」。点本轮第一条消息，确认「从这条开始并生成」；这条和下面的消息才录入聊天并参与模型调用，前面的旧消息忽略。也可选「本页全部参与」。点「返回，不录入」不录入聊天、不调用模型。未绑定档案时只识别名称，先在准备页绑定后再点击。
8. 之后每次点击直接读取本次画面并生成，重复气泡按消息顺序去重。不保留自动采集开关或画面稳定后的自动读取，也不会根据新消息后台生成回复。每次关闭软件后，近期上下文和本轮起点清除，重开后重新选起点。
9. 主页显示当前目的、对方最近说、对话参考 / 下一步建议、紧张度与回复候选。切换目的只保存并使旧建议失效；下次点击才生成。邀约、化解误会、认真沟通等目的会适度推进，不越过明确拒绝。
10. 误录或复测时，点「忘记选中聊天」，查看关联记录数量后确认。已有「新增联系人」可建立另一份资料；没有「重新开始本轮」按钮。

日常只需：打开对应微信单聊 → 确认首页联系人与目的 → 对方说完后点绿色按钮 → 选择回复、修改并确认发送。首次打开软件后需要选择一次本轮起点。人物资料不用每次重填，聊天中可在首页切换目的。

只有已保存、名称完全匹配的单聊使用档案生成。不同联系人应使用不同微信备注；OCR 名称绑定不是账户身份验证。群聊不使用伴侣档案。复制或填入后，发送由你确认。

## 记忆与待办

- **近期上下文**：每个会话独立内存缓冲，只有点击并确认的消息加入其中，关闭软件后清除。
- **长期记忆**：勾选点击后整理记忆与待办时，另调用起草模型整理重要事实、明确偏好和共同经历。只保存有角色对应依据的原文片段，按联系人加密保存；模型的性格 / 动机推测不自动成为事实。「长期记忆」页可查看、删去或手动补充。
- **补充历史**：完整旧对话默认仅本次内存，勾选保存后加密落盘。点评中的观察和原文记忆由你勾选采纳，再保存。
- **约定与待办**：双方讨论的安排自动整理成横条，包含原文时间、事项、地点（如有）。橙色待确认、绿色已确认、灰色已完成、红色已过期。可手动添加、编辑、完成或删除。
- **忘记选中聊天**：移除选中消息、相关自动记忆 / 待办、有对应依据的已采纳观察，以及相同的补充历史原文；手动背景资料保留。使正在生成的旧结果失效，当前运行期间可识别的旧气泡再次截图时继续忽略。以后新发的同一句话仍算新消息。

记忆整理只处理点击生成后已录入的聊天，间隔至少 20 秒，独立于回复生成；未确认的首次截图不参与整理。明确答应且有可确定日期的安排才自动标为已确认；含「可能」「改天」或日期不明的安排保持待确认。实时对话的相对日期按采集当天推算；旧历史没有可靠日期时不推算。时间、地点和识别结果请核对，可在待办中修正。提醒目前体现在软件里的「今天」/「已过期」标记，不提供关闭软件后的系统通知。

忘记只影响本程序的上下文和相关本地记录，不删除微信原消息，也不能撤回已经发给服务商的请求。重启后重新读取微信旧画面、或主动重新导入旧历史，会再次把其中的文字作为输入；复测时建议让新一轮对话显示在窗口中。没有可辨别顺序的完全相同截图，无法仅靠 OCR 判断究竟是旧消息还是重发。

## 隐私

这是本地界面加云端模型。回复会发送相关资料、历史和聊天文字到所选判断与起草服务商；历史点评、自动记忆与待办整理仅调用起草服务商。

档案、长期记忆和待办存放于 `%LOCALAPPDATA%\JevPartnerChat\private\profiles.dpapi`，使用 Windows 当前用户 DPAPI 加密。实时完整聊天和候选回复不自动落盘；重要原文片段会作为长期记忆保存。全局 `config.json` 明文；API Key 沿用 Windows 用户环境变量方式，未加密。详见 [PRIVACY.md](PRIVACY.md)。

## 开发与验证

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm jev.spec
```

构建产物为 `dist\jev-partner-chat`。`tools/partner_preview.py` 用虚构资料生成界面检查图；`tools/partner_smoke.py` 显式调用已配置的云端 API，可能计费，只发送脚本内虚构资料。普通单元测试不联网。

## 许可与公开发布

保留上游 [LICENSE](LICENSE)、[NOTICE](NOTICE) 与署名。项目源码沿用 MIT；打包依赖含 GPLv3 / LGPL 等组件，分发遵守各组件许可。完整文件夹附带许可说明和可修改源码。

源代码包排除个人配置、密钥、加密档案、真实聊天与截图。公开发布前仍需检查文件与提交历史。
