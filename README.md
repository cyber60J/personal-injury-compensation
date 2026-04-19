# Personal-Injury-Compensation 人身伤害赔偿脚本工具

此目录包含用于人身伤害赔偿案件的相关脚本工具。

## 功能规划

1. **赔偿金计算器** - 根据伤残等级、医疗费用、误工费等计算总赔偿金额
2. **案件管理工具** - 管理案件信息、时间节点、文件资料
3. **法律文书生成** - 自动生成赔偿协议、起诉状等法律文书
4. **数据统计与分析** - 分析赔偿案例数据，提供参考标准
5. **统计数据收集器** - 自动收集全国各地区人身损害赔偿核心年度统计数据

## 文件结构

```
Personal-Injury-Compensation/
├── README.md
├── compensation_calculator.py    # 赔偿金计算脚本
├── case_manager.py               # 案件管理脚本
├── document_generator.py         # 法律文书生成脚本
├── data_collector.py             # 统计数据收集脚本
├── requirements.txt              # Python依赖包
├── config/                       # 配置文件目录
├── data/                         # 数据文件目录
└── templates/                    # 文书模板目录
```

## 使用方法

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 赔偿金计算器
```bash
python compensation_calculator.py
```

### 3. 案件管理工具
```bash
python case_manager.py
```

### 4. 法律文书生成器
```bash
python document_generator.py
```

### 5. 统计数据收集器
```bash
# 基本用法（收集所有地区2021-2025年数据）
python data_collector.py

# 指定年份范围
python data_collector.py --start-year 2022 --end-year 2024

# 仅收集特定地区数据
python data_collector.py --region "江苏省"

# 不从上次进度恢复（重新开始）
python data_collector.py --no-resume

# 指定输出文件名
python data_collector.py --output "赔偿统计数据.xlsx"

# 查看帮助
python data_collector.py --help
```

数据收集器功能说明：
- 自动收集全国31个省、自治区、直辖市 + 5个计划单列市（深圳、厦门、宁波、青岛、大连）的统计数据
- 覆盖年份：2021-2025年（可配置）
- 收集6项核心数据：城镇居民人均可支配收入、城镇居民人均消费支出、城镇非私营单位年平均工资等
- 支持断点续爬：中断后可从中断处继续运行
- 输出格式：Excel文件（`人身损害赔偿统计数据_2021-2025.xlsx`）

**配置说明**：
脚本中的地区统计局URL需要根据实际情况更新。请在`data_collector.py`的`REGION_STATS_URLS`字典中更新各地区统计局的准确URL。

**运行提示**：
- 首次运行会收集所有数据，可能需要较长时间（数小时）
- 网络不稳定时脚本会自动重试
- 数据会实时保存到`data_collection_status.json`，可随时中断

## 法律声明

本工具仅供参考，不构成法律意见。具体赔偿金额应以法院判决或专业律师意见为准。

## 开发计划

- [ ] 基础赔偿金计算功能
- [ ] 案件信息管理功能
- [ ] 法律文书模板
- [ ] 数据可视化功能
- [ ] 用户界面优化