# task26100489

周排班复制库（纯内存，由上层直接调用，不负责保存排班）。

## 能力

- `shiftcopy.build_copy_plan(employees, existing_shifts, leaves, zone_name, target_week_start)`：
  把当地开始日期属于上一周的全部班次复制到目标周（两端点当地日期各推进 7 天、
  钟面时分与员工不变）。任一班次出现 DST 空隙、转换后结束不晚于开始、UTC 区间
  重叠或落在已批准休假内，整批抛 `CopyPlanError`，不返回部分方案；超工时仅产生
  `CopyPlan.warnings`。
- `shiftcopy.weekly_minutes(shifts, zone_name, week_start)`：按实际经过分钟数，
  只累计落在该当地周（周一 00:00 至下周一 00:00）内的部分，返回
  `{employee_id: minutes}`。

## 约定

- 时区仅支持 `America/New_York` 与 `Australia/Lord_Howe`，日期范围 2020–2035。
- 班次为含开始、不含结束的半开区间，端点落在 15 分钟刻度上。
- 换时处理：目标端点落在不存在的本地时刻整批失败；重复时刻优先选择与源端点
  UTC 偏移相同的候选，无匹配时取 UTC 较早者。
- 休假起止日期均为当地全天（含首尾），班次恰在休假首日零点结束不算冲突。

## 运行测试

```bash
python3 -m pytest tests/ -q     # 全部验收测试（含性能预算）
python3 tests/test_perf.py      # 可重复运行的耗时检查（150 员工 / 500 待复制 / 1500 存量）
```
