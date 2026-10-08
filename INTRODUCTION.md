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
