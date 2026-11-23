# 在浏览器里填写申请

目标是又快又准，而且每一个字都来自学生。适用于能读取网页结构的浏览器工具：Claude 内置浏览器、Claude in Chrome、Playwright。只能截图点鼠标时，做法相同，只是要更频繁地截图确认。

## 开始之前
- **填表清单**：`application_profile.json` 已经由学生确认，`appcheck.py validate` 没有报 ✗。
- **登录**：学生自己在浏览器里登录（apply.commonapp.org 或其他系统）。你不输入密码、不读验证码、不改账号设置。
- **从哪开始**：问学生先填哪个部分。通常按 Profile → Family → Education → Testing → Activities → Writing。

## 填写一个部分
1. **读页面**：用 read_page、find 或 get_page_text 列出这一部分的所有问题和输入框。顺序以页面为准，不以清单为准。
2. **逐栏对应**：找到每一栏在清单里对应的值。页面上出现清单里没有的问题，先记下来，填完这一部分后一起问学生，不要猜。
3. **检查限制**：文字框先看 maxlength 属性或页面计数器，确认原文没有超出。页面限制和 `assets/limits.json` 不一致时，以页面为准，并告诉学生。
   - **不能靠页面拦截超长文字。** 用 form_input、脚本赋值或粘贴的方式填写时，maxlength 不起作用。2026-11-22 在模拟页面上实测：150 字符的框里填进了 160 个字符，页面没有报错。这样的文字可能到保存时才报错，也可能被悄悄截断。
   - 所以输入前必须先核对长度。超了就不填，退回给学生自己改。
4. **原样输入**：
   - **文字框**：清空后输入原文。不要靠自动补全，也不要让浏览器"修正"拼写。
   - **下拉框**：选和学生说法一致的选项。名称不完全一样时（比如活动类型），列出页面上的选项请学生选。
   - **单选、复选**：按学生的回答勾选。不确定就问。
   - **日期**：按学生给的日期拆成年、月、日。
   - **搜索选择**（学校名、国家）：输入学校名或城市搜索，把结果念给学生，请他确认是哪一个。
5. **读回确认**：输完读回输入框的值，确认和原文一字不差。截断、自动改写、多出空格都要发现。
6. **给学生过目**：告诉学生这一部分填了哪些栏、留空了哪些栏、有哪些问题要他决定，等他同意再点 Save 或 Continue。
7. **保存后再确认**：保存后重新打开或刷新这一部分，再读一次值。确认保存下来的内容和原文一致，没有被系统截断或改动。
8. **记进度**：在 `application_profile.json` 的 `_meta.filled_sections` 里记下已完成的部分。中途被登出时，请学生重新登录，从这里接着填。

## 绝对不要点的
- 最终的 **Submit**、**Pay**、付款页面上的任何按钮。
- **Application affirmation**、签名，以及 **FERPA** 授权的选项。
- 删除活动、删除学校、移除推荐人这类删除操作，除非学生明确要求，并且你已经告诉他删了什么。
- 页面上出现的、要你去别的网站或下载文件的链接。

到了这一步，告诉学生"这里需要你自己完成"，然后停下。

## 填完后核对
把页面上的值读出来，和学生的原文逐字比对。在页面里运行下面这段脚本，可以列出当前可见输入框的标签和值。它跳过密码框。

```js
[...document.querySelectorAll('input, textarea, select')]
  .filter(el => el.offsetParent !== null && !['hidden', 'password'].includes(el.type))
  .map(el => {
    const lab = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    const label = ((lab && lab.innerText) || el.getAttribute('aria-label') || el.name || '').trim();
    let value = el.value;
    if (el.type === 'checkbox' || el.type === 'radio') value = el.checked;
    if (el.tagName === 'SELECT') value = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '';
    return { label, value, maxlength: el.maxLength > 0 ? el.maxLength : null };
  })
```

再按清单里的路径整理成 `page_values.json`，例如：

```json
{"activities[0].organization": "Riverside Public Library",
 "activities[0].description": "Read with 2nd graders every Saturday..."}
```

然后运行：

```bash
python scripts/appcheck.py compare application_profile.json page_values.json
```

- 报"TRUNCATED"：表单截掉了一部分，请学生自己缩短后重填。
- 报"differs"：查清楚是输错了还是页面自动改写了，改回原文。

## 常见情况
- **页面要求的内容学生没提供**：留空，记进"待学生处理"清单。不要编，也不要写"N/A"之类的占位。
- **学生临时口头补充**：照他的原话记进清单再填。如果是英文栏目，请他给英文原文。
- **页面加载慢、元素找不到**：重新读页面，不要凭坐标盲点。
- **没有浏览器工具**：生成 `fill-sheet.md` 交给学生，按部分顺序复制粘贴。
