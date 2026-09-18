-- First real tasks, triaged 2026-09-18 (see prompts/triage_prompt.md v1.1)

INSERT INTO tasks (
    user_id, title, notes, category, type,
    importance, urgency, action, status,
    remind_at, deadline
) VALUES
('bella', '投递虾皮·风险策略分析师', '', '工作学习', 'single',
 'high', 'high', 'now', 'todo',
 '2026-09-18 19:00', '2026-09-20 00:00'),

('bella', '投递国泰君安·交易风控岗', '', '工作学习', 'single',
 'high', 'high', 'now', 'todo',
 '2026-09-18 19:00', '2026-09-20 00:00'),

('bella', 'SQL 熟练度练习计划（一周内达到数据分析师面试水平）',
'7天冲刺计划：
Day1 (9/18) 基础语法：SELECT/WHERE/ORDER BY/DISTINCT/聚合函数(COUNT/SUM/AVG/MAX/MIN)/GROUP BY/HAVING。练习：LeetCode SQL Easy 10题
Day2 (9/19) JOIN全家桶：INNER/LEFT/RIGHT/FULL/SELF JOIN，多表关联逻辑。练习：Medium关联类 8题
Day3 (9/20) 子查询、CTE(WITH)、EXISTS/IN对比。练习：8题
Day4 (9/21) 窗口函数：ROW_NUMBER/RANK/DENSE_RANK/LAG/LEAD/累计求和——面试高频重点。练习：10题
Day5 (9/22) 业务场景实战：留存率、漏斗分析、同比环比、Top N、去重统计等数据分析师常考题型。练习：模拟真题5-8道
Day6 (9/23) 综合模拟测试：限时90分钟一套完整面试SQL卷 + 复盘错题
Day7 (9/24) 查漏补缺 + 高频面试题速查表整理 + 白板口述思路演练

资源：LeetCode SQL题库、SQLZoo、牛客网数据分析SQL真题（更贴近国内面试）',
 '工作学习', 'goal',
 'high', 'med', 'routine', 'routine',
 '2026-09-18 20:00', '2026-09-24 00:00');
