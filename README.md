# task26100489

## 周排班复制库（shiftcopy）

纯内存 Python 库，由上层直接调用；员工、现有排班和已批准休假由调用方提供，
不负责保存排班。仅支持 `America/New_York` 与 `Australia/Lord_Howe`，
日期范围 2020-2035，业务周为当地周一零点至下周一零点。

### 能力

- `generate_copy_plan(timezone, target_week_start, employees, existing_shifts, leaves)`
  把当地开始日期属于上一周的全部班次复制到目标周（钟面时分不变、员工不变）。
  换时缺口、复制后反转、UTC 区间重叠、休假冲突中的任一项都会导致整批失败
  （抛出 `CopyPlanError`，不返回部分方案）；超过员工周工时上限（默认 40h）
  仅在 `CopyPlan.warnings` 中产生警告。返回的 `CopyPlan.hours` 覆盖候选涉及的
  每个业务周（存量 + 候选）。
- `weekly_hours(timezone, week_start, shifts, employee_ids=None)`
  按实际经过分钟数计算指定当地周工时，只累计落在该周内的部分。

### 测试与性能

```bash
python3 -m pytest tests/   # 21 个自动化测试
python3 perf_check.py      # 150 员工 / 500 待复制 / 1500 存量，各项 < 200ms
```
