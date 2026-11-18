# 榆川台架复测质控

榆川计量组白班接收各台架导出的具名成对读数。计量员为每台架登记两轴的换算，台架员提交读数并领回批号。计量员封存批次，质控员按所选封存件签发合批门槛报告。到期作业清理原始行后，夜班仍能领取旧报告、清理回执和封存件，并用旧封存号重新核账。

## 运行

使用 Python 3.11 标准库，从项目根目录运行。

```sh
python3 -B -m cli init workshop.sqlite3
python3 -B -m unittest discover -v -s tests -t . -p 'test_*.py'
python3 -B -m cli demo
```

`init` 可重复执行，补建缺失的表和轴登记，沿用工作库中已有的项目、台架轴和业务记录。`demo` 从 `sample.json` 读取固定上报及截止点，在临时工作库完成登记、上报、封存、签发、到期、更正和重开。输出含原签发及逆序复查的实测结果，核账错误时命令非零退出。

## Python 接口

用 `db.open_database(path)` 打开工作库并在使用后关闭连接。调用 `db.initialize(db)` 初始化。部署可用 `initialize(db, projects=...)` 提供项目配置，元素为 `(ProjectAxes, 台架 BenchAxes 序列)`。项目轴定义统一轴名和单位，台架轴定义对应的输入轴名和单位。数据类在 `scales.projects` 中。写入入口各自拥有事务，逐次调用即可。

| 入口 | 输入与结果 |
| --- | --- |
| `scales.revisions.set_scale(db, project, bench, *, x, y)` | 两轴各传包含 `input_axis`、`input_unit`、`output_axis`、`output_unit`、`slope`、`offset` 的映射，返回新刻度修订号。轴名及单位须匹配所登记项目与台架。`require_scale_revision(db, scale_id)` 领取固定修订。 |
| `intake.batches.submit_batch(db, project, bench, submission_key, scale_id, rows, *, accepted_at, predecessor_id=None)` | `rows` 为 `(row_key, x, y)` 三元组的有限可迭代对象，空值用 `None`。返回批修订号。批身份由项目、台架、上报键组成。可指定同项目同台架的既存前批，形成追加式更正。 |
| `intake.store.load_batch_header(db, batch_id)`、`load_batch_rows(db, batch_id)` | 领取固定批头或原始行。原始行可用时返回元组，已清理或未知批返回 `None`。仍可用的空批返回空元组。 |
| `freeze.package.seal_batch(db, batch_id)` | 对一个原始行仍可用的批修订封存，返回 `SealedEvidence`。同批在此期间再次封存时领取原件。`freeze.catalog.get_seal(db, seal_id)` 按号领取保存的来源及统一坐标统计。 |
| `review.reports.issue_review(db, seal_ids, threshold)` | 选取同项目的非空、互异封存号集合。返回 `QualityReport`，含报告号、项目、按号升序的封存集合、门槛、有效对数、精确 `q` 或 `None`，以及 `passed`。`get_review(db, report_id)` 读取原签发结果。 |
| `retention.purge.expire_batch(db, batch_id, policy, cutoff)` | `policy` 为 `retention.policy.RetentionPolicy(timedelta(...))`。截止点达到到期点且本修订有已提交封存时，清理原始行并返回 `ExpiryReceipt`。同批重试返回原回执。`retention.receipts.lookup_receipt(db, batch_id)` 可独立领取。 |

编号为正的 SQLite 整数。未知封存号、报告号、批号查询及回执查询返回 `None`。未知修订、非法输入、冲突重投和不具备清理资格的写请求抛出 `ValueError`。上报键和行号使用非空文本，同批的行号唯一。原样重投按规范读数及行身份比较，传输顺序与重试提供的受理时间不影响批身份。源行可用时进一步核对实际读数，清理后沿用原规范内容的摘要。受理时间和截止点用含时区的 `datetime`，统一按 UTC 比较。SQLite 错误向调用方传播，封存、报告、清理等写操作在提交失败时回滚。

## 计算口径

读数、斜率、偏移、门槛接受整数、`Fraction` 和 `Fraction` 可解析的数值字符串。布尔值和浮点数无效。单条配对在同一行同时有横纵读数时成立，两个不同的行号即使同值也各计一次。两轴分别用固定修订 `u = a*x+b`、`v = c*y+d` 换标，两条斜率都非零。封存保存项目、批修订号、刻度修订号及统一坐标下的 `n, sx, sy, sxx, syy, sxy`。

报告对选择的封存证据逐项相加，得到 `A = n*sxx-sx*sx`、`B = n*syy-sy*sy` 和 `C = n*sxy-sx*sy`。合批不足两对或 `A`、`B` 有一项为零时，报告仍保留选件和对数，`q=None`、`passed=False`。其余情况 `q = C*abs(C)/(A*B)`。门槛在 `[-1, 1]`，等于门槛时通过。数据库用规范有理数的分子、分母文本保存精确值。原始行临期清理与回执同次提交，旧报告按原号读取当时签发的数值和决定。

样例中的甲台架提交 `(0,0)`、`(1,1)`，乙台架 `(0,0)` 换为 `(2,0)`。三对的横纵交叉离差为零，所以 `n=3, q=0`，门槛 `1/2` 拒绝。测试另用独立闭式分数核对近满相关门槛，用 SQLite 延迟外键触发真实提交失败，并检查回滚与重开后的结果。
