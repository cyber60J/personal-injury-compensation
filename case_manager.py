#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人身伤害赔偿案件管理工具

功能：
1. 案件信息录入与保存
2. 案件状态跟踪
3. 时间节点提醒
4. 文件资料管理
5. 赔偿计算集成
"""

import json
import os
import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class CaseInfo:
    """案件信息类"""
    case_number: str
    injured_party: str
    accident_date: str
    accident_location: str
    responsible_party: str
    case_status: str  # 受理、审理、调解、结案等
    lawyer: str
    court: Optional[str] = None
    description: Optional[str] = None

@dataclass
class TimelineEvent:
    """时间线事件"""
    event_id: str
    case_number: str
    event_date: str
    event_type: str  # 立案、开庭、调解、判决等
    description: str
    completed: bool = False
    notes: Optional[str] = None

@dataclass
class Document:
    """案件文档"""
    doc_id: str
    case_number: str
    doc_type: str  # 起诉状、证据、鉴定报告、判决书等
    file_path: str
    upload_date: str
    description: Optional[str] = None

class CaseManager:
    """案件管理器"""

    def __init__(self, data_dir: str = "data/cases"):
        """初始化案件管理器"""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 案件存储文件
        self.cases_file = self.data_dir / "cases.json"
        self.timeline_file = self.data_dir / "timeline.json"
        self.documents_file = self.data_dir / "documents.json"

        # 加载数据
        self.cases = self._load_data(self.cases_file)
        self.timeline_events = self._load_data(self.timeline_file)
        self.documents = self._load_data(self.documents_file)

    def _load_data(self, file_path: Path) -> List[Dict]:
        """从JSON文件加载数据"""
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def _save_data(self, data: List[Dict], file_path: Path):
        """保存数据到JSON文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_case(self, case_info: CaseInfo):
        """添加新案件"""
        case_dict = asdict(case_info)
        self.cases.append(case_dict)
        self._save_data(self.cases, self.cases_file)
        print(f"案件 {case_info.case_number} 添加成功")

    def get_case(self, case_number: str) -> Optional[Dict]:
        """获取案件信息"""
        for case in self.cases:
            if case['case_number'] == case_number:
                return case
        return None

    def update_case_status(self, case_number: str, new_status: str):
        """更新案件状态"""
        for case in self.cases:
            if case['case_number'] == case_number:
                case['case_status'] = new_status
                self._save_data(self.cases, self.cases_file)
                print(f"案件 {case_number} 状态更新为 {new_status}")
                return
        print(f"未找到案件 {case_number}")

    def add_timeline_event(self, event: TimelineEvent):
        """添加时间线事件"""
        event_dict = asdict(event)
        self.timeline_events.append(event_dict)
        self._save_data(self.timeline_events, self.timeline_file)
        print(f"时间线事件 {event.event_id} 添加成功")

    def get_case_timeline(self, case_number: str) -> List[Dict]:
        """获取案件时间线"""
        return [event for event in self.timeline_events
                if event['case_number'] == case_number]

    def add_document(self, document: Document):
        """添加案件文档"""
        # 检查文件是否存在
        if not Path(document.file_path).exists():
            print(f"警告：文件 {document.file_path} 不存在")
            return

        doc_dict = asdict(document)
        self.documents.append(doc_dict)
        self._save_data(self.documents, self.documents_file)
        print(f"文档 {document.doc_id} 添加成功")

    def get_case_documents(self, case_number: str) -> List[Dict]:
        """获取案件相关文档"""
        return [doc for doc in self.documents
                if doc['case_number'] == case_number]

    def list_all_cases(self) -> List[Dict]:
        """列出所有案件"""
        return self.cases

    def search_cases(self, keyword: str) -> List[Dict]:
        """搜索案件"""
        results = []
        for case in self.cases:
            if (keyword in case['case_number'] or
                keyword in case['injured_party'] or
                keyword in case['responsible_party'] or
                (case['description'] and keyword in case['description'])):
                results.append(case)
        return results

    def generate_case_report(self, case_number: str) -> Dict:
        """生成案件报告"""
        case = self.get_case(case_number)
        if not case:
            return {}

        timeline = self.get_case_timeline(case_number)
        documents = self.get_case_documents(case_number)

        return {
            'case_info': case,
            'timeline': timeline,
            'documents': documents,
            'report_generated': datetime.datetime.now().isoformat()
        }

def main():
    """主函数：命令行交互界面"""
    print("=" * 60)
    print("人身伤害赔偿案件管理工具")
    print("=" * 60)

    manager = CaseManager()

    while True:
        print("\n请选择操作：")
        print("1. 添加新案件")
        print("2. 查看所有案件")
        print("3. 搜索案件")
        print("4. 更新案件状态")
        print("5. 添加时间线事件")
        print("6. 添加文档")
        print("7. 生成案件报告")
        print("8. 退出")

        choice = input("\n请输入选项编号：").strip()

        if choice == "1":
            # 添加新案件
            case_number = input("案件编号：")
            injured_party = input("受害人姓名：")
            accident_date = input("事故日期（YYYY-MM-DD）：")
            accident_location = input("事故地点：")
            responsible_party = input("责任方：")
            case_status = input("案件状态：")
            lawyer = input("代理律师：")
            court = input("管辖法院（可选）：")
            description = input("案件描述（可选）：")

            case_info = CaseInfo(
                case_number=case_number,
                injured_party=injured_party,
                accident_date=accident_date,
                accident_location=accident_location,
                responsible_party=responsible_party,
                case_status=case_status,
                lawyer=lawyer,
                court=court if court else None,
                description=description if description else None
            )
            manager.add_case(case_info)

        elif choice == "2":
            # 查看所有案件
            cases = manager.list_all_cases()
            print(f"\n共 {len(cases)} 个案件：")
            for case in cases:
                print(f"{case['case_number']}: {case['injured_party']} - {case['case_status']}")

        elif choice == "3":
            # 搜索案件
            keyword = input("搜索关键词：")
            results = manager.search_cases(keyword)
            print(f"\n找到 {len(results)} 个匹配案件：")
            for case in results:
                print(f"{case['case_number']}: {case['injured_party']}")

        elif choice == "4":
            # 更新案件状态
            case_number = input("案件编号：")
            new_status = input("新状态：")
            manager.update_case_status(case_number, new_status)

        elif choice == "5":
            # 添加时间线事件
            case_number = input("案件编号：")
            event_id = input("事件ID：")
            event_date = input("事件日期（YYYY-MM-DD）：")
            event_type = input("事件类型：")
            event_desc = input("事件描述：")
            completed = input("是否完成（y/n）：").lower() == 'y'
            notes = input("备注（可选）：")

            event = TimelineEvent(
                event_id=event_id,
                case_number=case_number,
                event_date=event_date,
                event_type=event_type,
                description=event_desc,
                completed=completed,
                notes=notes if notes else None
            )
            manager.add_timeline_event(event)

        elif choice == "6":
            # 添加文档
            print("文档添加功能需要文件路径，请确保文件已存在")
            case_number = input("案件编号：")
            doc_id = input("文档ID：")
            doc_type = input("文档类型：")
            file_path = input("文件路径：")
            description = input("文档描述（可选）：")

            document = Document(
                doc_id=doc_id,
                case_number=case_number,
                doc_type=doc_type,
                file_path=file_path,
                upload_date=datetime.datetime.now().strftime("%Y-%m-%d"),
                description=description if description else None
            )
            manager.add_document(document)

        elif choice == "7":
            # 生成案件报告
            case_number = input("案件编号：")
            report = manager.generate_case_report(case_number)
            if report:
                report_file = f"data/reports/{case_number}_report.json"
                os.makedirs(os.path.dirname(report_file), exist_ok=True)
                with open(report_file, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print(f"报告已保存至 {report_file}")
            else:
                print("未找到案件")

        elif choice == "8":
            print("退出案件管理工具")
            break

        else:
            print("无效选项，请重新选择")

if __name__ == "__main__":
    main()