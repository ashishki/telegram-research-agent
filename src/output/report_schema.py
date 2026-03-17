from dataclasses import dataclass, field


@dataclass
class ReportMeta:
    week_label: str
    date_range: str
    generated_at: str
    post_count: int
    channel_count: int


@dataclass
class KeyFinding:
    title: str
    body: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ReportSection:
    heading: str
    body: str


@dataclass
class EvidenceItem:
    id: str
    channel: str
    date: str
    excerpt: str
    url: str


@dataclass
class ProjectRelevanceItem:
    name: str
    score: float
    notes: str


@dataclass
class ResearchReport:
    meta: ReportMeta
    executive_summary: list[str] = field(default_factory=list)
    key_findings: list[KeyFinding] = field(default_factory=list)
    sections: list[ReportSection] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    project_relevance: list[ProjectRelevanceItem] = field(default_factory=list)
    confidence_notes: str = ""


@dataclass
class DigestResult:
    week_label: str
    output_path: str
    post_count: int
    json_path: str
