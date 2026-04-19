#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
法律文书生成工具

功能：
1. 赔偿协议生成
2. 起诉状生成
3. 调解协议生成
4. 法律文书模板管理
"""

import os
import json
import datetime
from pathlib import Path
from typing import Dict, Any

class DocumentGenerator:
    """法律文书生成器"""

    def __init__(self, templates_dir: str = "templates"):
        """初始化生成器"""
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def load_template(self, template_name: str) -> str:
        """加载模板文件"""
        template_path = self.templates_dir / f"{template_name}.txt"
        if template_path.exists():
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # 返回默认模板
            if template_name == "compensation_agreement":
                return self._get_default_compensation_agreement()
            elif template_name == "complaint":
                return self._get_default_complaint()
            elif template_name == "mediation_agreement":
                return self._get_default_mediation_agreement()
            else:
                raise FileNotFoundError(f"模板 {template_name} 不存在")

    def save_template(self, template_name: str, content: str):
        """保存模板文件"""
        template_path = self.templates_dir / f"{template_name}.txt"
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"模板 {template_name} 已保存")

    def generate_document(self, template_name: str, data: Dict[str, Any]) -> str:
        """生成文书"""
        template = self.load_template(template_name)

        # 替换模板中的占位符
        for key, value in data.items():
            placeholder = "{" + key + "}"
            template = template.replace(placeholder, str(value))

        # 替换日期相关占位符
        today = datetime.date.today()
        template = template.replace("{年}", str(today.year))
        template = template.replace("{月}", str(today.month))
        template = template.replace("{日}", str(today.day))

        return template

    def save_document(self, content: str, output_path: str):
        """保存生成的文书"""
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"文书已保存至：{output_path}")

    def _get_default_compensation_agreement(self) -> str:
        """获取默认赔偿协议模板"""
        return """赔偿协议

甲方（赔偿义务人）：________________________
身份证号/统一社会信用代码：________________________
住所地：________________________
联系电话：________________________

乙方（赔偿权利人）：________________________
身份证号：________________________
住所地：________________________
联系电话：________________________

鉴于：
1. {accident_date}，在{accident_location}发生人身伤害事故，导致乙方受伤。
2. 经{assessment_institution}鉴定，乙方伤残等级为{disability_level}级。
3. 双方就赔偿事宜协商一致，达成如下协议：

一、赔偿金额
甲方同意向乙方支付赔偿金共计人民币{total_compensation}元（大写：{total_compensation_chinese}）。

二、赔偿明细
1. 医疗费：{medical_expenses}元
2. 误工费：{loss_of_income}元
3. 护理费：{nursing_fee}元
4. 交通费：{transportation_fee}元
5. 住院伙食补助费：{hospital_meal_subsidy}元
6. 营养费：{nutrition_fee}元
7. 残疾赔偿金：{disability_compensation}元
8. 精神损害抚慰金：{mental_distress}元
9. 被扶养人生活费：{dependent_support}元
10. 其他费用：{other_expenses}元

三、支付方式
1. 本协议签订后{payment_days}日内，甲方向乙方支付全部赔偿金。
2. 支付方式：银行转账
   开户行：________________________
   账户名：________________________
   账号：________________________

四、双方权利义务
1. 甲方按约定支付赔偿金后，乙方不得就此事再向甲方主张任何权利。
2. 乙方收到赔偿金后，应向甲方出具收据。
3. 双方确认本协议为解决本次事故赔偿事宜的最终协议。

五、违约责任
任何一方违反本协议约定，应承担违约责任，向守约方支付违约金{penalty_amount}元。

六、争议解决
因本协议引起的或与本协议有关的任何争议，双方应友好协商解决；协商不成的，任何一方均有权向{jurisdiction_court}提起诉讼。

七、其他
1. 本协议一式两份，甲乙双方各执一份，具有同等法律效力。
2. 本协议自双方签字盖章之日起生效。

甲方（签字/盖章）：________________________
日期：{year}年{month}月{day}日

乙方（签字/盖章）：________________________
日期：{year}年{month}月{day}日

见证人（如有）：________________________
日期：{year}年{month}月{day}日"""

    def _get_default_complaint(self) -> str:
        """获取默认起诉状模板"""
        return """民事起诉状

原告：{plaintiff_name}
性别：{plaintiff_gender}
出生日期：{plaintiff_birthdate}
身份证号：{plaintiff_id}
住所地：{plaintiff_address}
联系电话：{plaintiff_phone}

被告：{defendant_name}
性别：{defendant_gender}
出生日期：{defendant_birthdate}
身份证号：{defendant_id}
住所地：{defendant_address}
联系电话：{defendant_phone}

诉讼请求：
1. 判令被告赔偿原告医疗费{medical_expenses}元；
2. 判令被告赔偿原告误工费{loss_of_income}元；
3. 判令被告赔偿原告护理费{nursing_fee}元；
4. 判令被告赔偿原告交通费{transportation_fee}元；
5. 判令被告赔偿原告住院伙食补助费{hospital_meal_subsidy}元；
6. 判令被告赔偿原告营养费{nutrition_fee}元；
7. 判令被告赔偿原告残疾赔偿金{disability_compensation}元；
8. 判令被告赔偿原告精神损害抚慰金{mental_distress}元；
9. 判令被告承担本案诉讼费用。

事实与理由：
{accident_date}，在{accident_location}发生交通事故（或其他事故），导致原告受伤。事故发生后，原告被送往{医院名称}治疗，住院{住院天数}天。经{鉴定机构}鉴定，原告构成{伤残等级}级伤残。

被告作为事故责任方，应承担全部赔偿责任。原告多次与被告协商赔偿事宜，但被告拒不支付赔偿金。为维护原告合法权益，特向贵院提起诉讼。

此致
{法院名称}

起诉人（签字）：________________________
{year}年{month}月{day}日

附：
1. 起诉状副本{副本份数}份
2. 证据材料清单
3. 原告身份证复印件
4. 医疗费票据
5. 伤残鉴定报告"""

    def _get_default_mediation_agreement(self) -> str:
        """获取默认调解协议模板"""
        return """调解协议

甲方（赔偿义务人）：{defendant_name}
身份证号：{defendant_id}
住所地：{defendant_address}
联系电话：{defendant_phone}

乙方（赔偿权利人）：{plaintiff_name}
身份证号：{plaintiff_id}
住所地：{plaintiff_address}
联系电话：{plaintiff_phone}

调解人：{mediator_name}
单位：{mediator_institution}

经{法院名称/调解组织}主持调解，甲乙双方就人身伤害赔偿事宜达成如下协议：

一、事故基本情况
{accident_date}，在{accident_location}发生事故，造成乙方受伤。

二、赔偿金额
甲方同意赔偿乙方各项损失共计人民币{total_compensation}元。

三、支付方式
1. 第一期：本协议签订后{first_payment_days}日内支付{first_payment_amount}元；
2. 第二期：{second_payment_date}前支付{second_payment_amount}元；
3. 第三期：{third_payment_date}前支付{third_payment_amount}元。

四、双方承诺
1. 甲方按约定支付赔偿金；
2. 乙方收到全部赔偿金后，不再就此事追究甲方任何责任；
3. 双方同意向法院申请司法确认。

五、其他
1. 本协议一式三份，甲乙双方及调解人各执一份；
2. 本协议自双方签字之日起生效。

甲方（签字）：________________________
日期：{year}年{month}月{day}日

乙方（签字）：________________________
日期：{year}年{month}月{day}日

调解人（签字）：________________________
日期：{year}年{month}月{day}日"""

    def number_to_chinese(self, num: float) -> str:
        """数字转中文大写"""
        chinese_numbers = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"]
        chinese_units = ["", "拾", "佰", "仟", "万", "拾", "佰", "仟", "亿"]

        # 简单实现，完整实现较复杂
        integer_part = int(num)
        decimal_part = int(round((num - integer_part) * 100))

        result = ""
        if integer_part > 0:
            # 处理整数部分
            str_num = str(integer_part)
            length = len(str_num)
            for i, char in enumerate(str_num):
                digit = int(char)
                if digit != 0:
                    result += chinese_numbers[digit] + chinese_units[length - i - 1]
                else:
                    # 处理零
                    if result and result[-1] != "零":
                        result += "零"
            result += "元"

        if decimal_part > 0:
            # 处理小数部分
            jiao = decimal_part // 10
            fen = decimal_part % 10

            if jiao > 0:
                result += chinese_numbers[jiao] + "角"
            if fen > 0:
                result += chinese_numbers[fen] + "分"
        else:
            result += "整"

        return result if result else "零元整"

def main():
    """主函数：命令行交互界面"""
    print("=" * 60)
    print("法律文书生成工具")
    print("=" * 60)

    generator = DocumentGenerator()

    while True:
        print("\n请选择操作：")
        print("1. 生成赔偿协议")
        print("2. 生成起诉状")
        print("3. 生成调解协议")
        print("4. 管理模板")
        print("5. 退出")

        choice = input("\n请输入选项编号：").strip()

        if choice == "1":
            # 生成赔偿协议
            print("\n请输入赔偿协议数据：")
            data = {
                "accident_date": input("事故日期："),
                "accident_location": input("事故地点："),
                "assessment_institution": input("鉴定机构："),
                "disability_level": input("伤残等级："),
                "total_compensation": input("总赔偿金额："),
                "medical_expenses": input("医疗费："),
                "loss_of_income": input("误工费："),
                "nursing_fee": input("护理费："),
                "transportation_fee": input("交通费："),
                "hospital_meal_subsidy": input("住院伙食补助费："),
                "nutrition_fee": input("营养费："),
                "disability_compensation": input("残疾赔偿金："),
                "mental_distress": input("精神损害抚慰金："),
                "dependent_support": input("被扶养人生活费："),
                "other_expenses": input("其他费用："),
                "payment_days": input("支付期限（天）："),
                "penalty_amount": input("违约金金额："),
                "jurisdiction_court": input("管辖法院："),
            }

            # 转换金额大写
            try:
                total = float(data["total_compensation"])
                data["total_compensation_chinese"] = generator.number_to_chinese(total)
            except:
                data["total_compensation_chinese"] = "（金额转换失败）"

            content = generator.generate_document("compensation_agreement", data)

            output_path = input("保存路径（默认：output/赔偿协议.txt）：").strip()
            if not output_path:
                output_path = "output/赔偿协议.txt"

            generator.save_document(content, output_path)

        elif choice == "2":
            # 生成起诉状
            print("\n请输入起诉状数据：")
            data = {
                "plaintiff_name": input("原告姓名："),
                "plaintiff_gender": input("原告性别："),
                "plaintiff_birthdate": input("原告出生日期："),
                "plaintiff_id": input("原告身份证号："),
                "plaintiff_address": input("原告住所地："),
                "plaintiff_phone": input("原告联系电话："),
                "defendant_name": input("被告姓名："),
                "defendant_gender": input("被告性别："),
                "defendant_birthdate": input("被告出生日期："),
                "defendant_id": input("被告身份证号："),
                "defendant_address": input("被告住所地："),
                "defendant_phone": input("被告联系电话："),
                "medical_expenses": input("医疗费："),
                "loss_of_income": input("误工费："),
                "nursing_fee": input("护理费："),
                "transportation_fee": input("交通费："),
                "hospital_meal_subsidy": input("住院伙食补助费："),
                "nutrition_fee": input("营养费："),
                "disability_compensation": input("残疾赔偿金："),
                "mental_distress": input("精神损害抚慰金："),
                "accident_date": input("事故日期："),
                "accident_location": input("事故地点："),
                "医院名称": input("医院名称："),
                "住院天数": input("住院天数："),
                "鉴定机构": input("鉴定机构："),
                "伤残等级": input("伤残等级："),
                "法院名称": input("法院名称："),
                "副本份数": input("副本份数："),
            }

            content = generator.generate_document("complaint", data)

            output_path = input("保存路径（默认：output/起诉状.txt）：").strip()
            if not output_path:
                output_path = "output/起诉状.txt"

            generator.save_document(content, output_path)

        elif choice == "3":
            # 生成调解协议
            print("\n请输入调解协议数据：")
            data = {
                "defendant_name": input("被告姓名："),
                "defendant_id": input("被告身份证号："),
                "defendant_address": input("被告住所地："),
                "defendant_phone": input("被告联系电话："),
                "plaintiff_name": input("原告姓名："),
                "plaintiff_id": input("原告身份证号："),
                "plaintiff_address": input("原告住所地："),
                "plaintiff_phone": input("原告联系电话："),
                "mediator_name": input("调解人姓名："),
                "mediator_institution": input("调解人单位："),
                "法院名称/调解组织": input("法院名称/调解组织："),
                "accident_date": input("事故日期："),
                "accident_location": input("事故地点："),
                "total_compensation": input("总赔偿金额："),
                "first_payment_days": input("第一期支付天数："),
                "first_payment_amount": input("第一期支付金额："),
                "second_payment_date": input("第二期支付日期："),
                "second_payment_amount": input("第二期支付金额："),
                "third_payment_date": input("第三期支付日期："),
                "third_payment_amount": input("第三期支付金额："),
            }

            content = generator.generate_document("mediation_agreement", data)

            output_path = input("保存路径（默认：output/调解协议.txt）：").strip()
            if not output_path:
                output_path = "output/调解协议.txt"

            generator.save_document(content, output_path)

        elif choice == "4":
            # 管理模板
            print("\n模板管理：")
            print("1. 查看现有模板")
            print("2. 编辑模板")
            print("3. 返回")

            sub_choice = input("\n请输入选项编号：").strip()

            if sub_choice == "1":
                templates_dir = Path("templates")
                if templates_dir.exists():
                    templates = list(templates_dir.glob("*.txt"))
                    print(f"\n现有模板（{len(templates)}个）：")
                    for template in templates:
                        print(f"  - {template.stem}")
                else:
                    print("模板目录不存在")

            elif sub_choice == "2":
                template_name = input("模板名称（不带扩展名）：")
                try:
                    content = generator.load_template(template_name)
                    print(f"\n当前模板内容：\n{content[:500]}...")

                    edit = input("\n是否编辑？（y/n）：").lower()
                    if edit == 'y':
                        print("请粘贴新模板内容（输入END结束）：")
                        lines = []
                        while True:
                            line = input()
                            if line == "END":
                                break
                            lines.append(line)
                        new_content = "\n".join(lines)
                        generator.save_template(template_name, new_content)
                except FileNotFoundError as e:
                    print(e)

            elif sub_choice == "3":
                continue

        elif choice == "5":
            print("退出文书生成工具")
            break

        else:
            print("无效选项，请重新选择")

if __name__ == "__main__":
    main()