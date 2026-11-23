# 其他申请系统

原则和 Common App 相同：只填学生给的原文，限制以页面显示为准，不点提交和付款。

## UC Application（加州大学）
核对日期：2026-11-22。来源：admission.universityofcalifornia.edu 的 first-year 页面。

- **一份申请可以报多个 UC 校区**，和 Common App 是两套独立系统，答案不会互通。学生要在 UC 系统里重新填写。可以从 `application_profile.json` 复制学生已经给过的原文，但 UC 的栏目和限制不同，要逐项对照。
- **Personal insight questions**：8 道题选 4 道，每篇最多 350 词。没有必选题，选哪 4 道由学生决定。8 个主题：
  1. 领导经历
  2. 创造力
  3. 最突出的才能
  4. 利用教育机会或克服教育障碍
  5. 最大的挑战
  6. 让你着迷的学科
  7. 让学校或社区变得更好
  8. 为什么你是合适的 UC 申请人
  
  检查字数：`python scripts/appcheck.py essay --file piq1.txt --max 350`
- **Activities and awards**：6 类，分别是 award or honor、educational preparation programs、extracurricular activity、other coursework、volunteering/community service、work experience。条目上限和每栏字符限制只在登录后的系统里显示，填表时从页面读出来，不要沿用 Common App 的 50/100/150。
- **Additional comments**：用于说明特殊情况。UC 说它"不应该是一篇文章"。
- **时间**：fall 2027 入学的申请 8 月 1 日开放，提交期是 2026 年 10 月 1 日至 11 月 30 日。
- **考试**：UC 不把 SAT/ACT 用于录取和奖学金决定。

## Coalition with Scoir
少数学校使用。文书题目、栏目和限制都以系统页面为准。学生给原文后照填。

## 学校自己的系统
例如 MIT 等，有自己的短问题和活动栏。做法：
1. 读页面上每个问题的说明和字数或字符限制。
2. 请学生提供每题的原文。
3. 用 `appcheck.py count` 或 `essay --max N` 检查长度，超出就告诉学生。
4. 照原文填写。不要把 Common App 的文书"改写"成适合这所学校的版本，这属于生成新内容。

## 各校补充文书（Writing supplements）
在 Common App 的 My Colleges 里，每所学校单独设置。题目、字数各不相同，以页面为准。学生给了原文才填，不代写。
