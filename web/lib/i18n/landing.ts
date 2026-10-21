import type { Locale } from "@/lib/i18n/types";

export type LandingMessages = {
  nav: {
    pipeline: string;
    documents: string;
    capabilities: string;
    personas: string;
    stack: string;
    signIn: string;
    explore: string;
    home: string;
    openMenu: string;
    closeMenu: string;
    switchLight: string;
    switchDark: string;
    language: string;
  };
  hero: {
    badgeOnPrem: string;
    badgeLocal: string;
    titleLine1: string;
    titleLine2: string;
    rotatingWords: string[];
    subtitle: string;
    accountNote: string;
    signIn: string;
    seeHow: string;
    statDocTypes: string;
    statHybridRag: string;
    statRbac: string;
    chatLines: string[];
    machines: string;
    openWos: string;
    active: string;
    askNeo: string;
    docsIndexed: string;
    avgAnswer: string;
    sample: string;
  };
  marquee: string[];
  stats: { value: string; label: string }[];
  pipeline: {
    eyebrow: string;
    title: string;
    titleHighlight: string;
    subtitle: string;
    steps: { title: string; detail: string }[];
  };
  documents: {
    eyebrow: string;
    title: string;
    titleHighlight: string;
    subtitle: string;
    categories: { name: string; types: string[] }[];
  };
  features: {
    eyebrow: string;
    title: string;
    titleHighlight: string;
    subtitle: string;
    items: { title: string; description: string }[];
  };
  deepDive: {
    eyebrow: string;
    title: string;
    subtitle: string;
    tabs: {
      id: string;
      label: string;
      headline: string;
      bullets: string[];
      endpoint?: string;
    }[];
    quickLinks: { label: string; path: string }[];
  };
  personas: {
    eyebrow: string;
    title: string;
    subtitle: string;
    homeRoute: string;
    items: { role: string; user: string; access: string; routes: string[]; home: string }[];
  };
  neo: {
    eyebrow: string;
    title: string;
    titleHighlight: string;
    subtitle: string;
    installTitle: string;
    installDesc: string;
    offlineTitle: string;
    offlineDesc: string;
    feedbackTitle: string;
    feedbackDesc: string;
    roiEyebrow: string;
    roi: { title: string; desc: string }[];
  };
  stack: {
    eyebrow: string;
    title: string;
    subtitle: string;
    items: { name: string; role: string }[];
    footnote: string;
  };
  cta: {
    title: string;
    subtitle: string;
    getStarted: string;
    signIn: string;
    footnote: string;
  };
  footer: {
    copyright: string;
    privacy: string;
    signIn: string;
  };
};

const landingTh: LandingMessages = {
  nav: {
    pipeline: "Pipeline",
    documents: "เอกสาร",
    capabilities: "ความสามารถ",
    personas: "บทบาทผู้ใช้",
    stack: "เทคโนโลยี",
    signIn: "เข้าสู่ระบบ",
    explore: "สำรวจ",
    home: "หน้าแรก",
    openMenu: "เปิดเมนู",
    closeMenu: "ปิดเมนู",
    switchLight: "เปลี่ยนเป็นธีมสว่าง",
    switchDark: "เปลี่ยนเป็นธีมมืด",
    language: "เปลี่ยนภาษา",
  },
  hero: {
    badgeOnPrem: "ติดตั้งในโรงงาน — ข้อมูลอยู่ในเครือข่ายคุณ",
    badgeLocal: "เดโมบนอุปกรณ์นี้ — ข้อมูลอยู่ในเครือข่ายคุณ",
    titleLine1: "อนาคตของโรงงาน",
    titleLine2: "เริ่มจาก",
    rotatingWords: ["ความรู้", "งานซ่อม", "เอกสาร", "ใบสั่งงาน", "อินไซต์"],
    subtitle:
      "Neo Chat — ค้นหาคู่มือ ถาม AI จัดการเครื่องจักรและใบสั่งงาน ออกแบบสำหรับโรงงานจริง ปลอดภัยบนเครือข่ายของคุณ",
    accountNote: "บัญชีผู้ใช้สร้างโดยผู้ดูแลโรงงาน — เข้าสู่ระบบด้วยข้อมูลที่ได้รับ",
    signIn: "เข้าสู่ระบบ",
    seeHow: "ดูวิธีการทำงาน",
    statDocTypes: "15 ประเภทเอกสาร",
    statHybridRag: "Hybrid RAG",
    statRbac: "สิทธิ์ตามโรงงาน",
    chatLines: [
      "แก้เซอร์โวร้อนเกินที่ MC-001 ยังไง?",
      "กำลังค้นหาคู่มือ + ประวัติซ่อม…",
      "สาเหตุ: พัดระบายอุดตัน ดู SOP §4.2",
    ],
    machines: "เครื่องจักร",
    openWos: "ใบสั่งงานเปิด",
    active: "● ทำงาน",
    askNeo: "ถาม Neo Chat",
    docsIndexed: "เอกสารจัดทำดัชนี",
    avgAnswer: "เวลาตอบเฉลี่ย",
    sample: "ตัวอย่าง",
  },
  marquee: [
    "Hybrid RAG",
    "Text-to-SQL",
    "43-case eval gate",
    "Qdrant sharding",
    "Celery ingest",
    "Job-position ACL",
    "Cross-encoder rerank",
    "Verified Q&A cache",
    "Shift handover",
    "RCA analyze",
    "Predictive at-risk",
    "Inventory insights",
    "SSE alerts",
    "Offline PWA",
    "Floor feedback",
    "Thai synthesis",
    "Documents Hub",
    "Prometheus metrics",
  ],
  stats: [
    { value: "15", label: "ประเภทเอกสาร YAML" },
    { value: "21", label: "โมดูล API ที่ /api/v1" },
    { value: "4-level", label: "RAG fallback ladder" },
    { value: "43", label: "เคส eval ใน CI" },
    { value: "1024", label: "มิติ embedding (bge-m3)" },
    { value: "100%", label: "On-premise · localhost" },
  ],
  pipeline: {
    eyebrow: "Pipeline",
    title: "จากอัปโหลดถึงการตัดสินใจ —",
    titleHighlight: "หนึ่ง pipeline แบบ async",
    subtitle:
      "อัปโหลดเอกสารผ่าน /upload ติดตามสถานะที่ /api/v1/ingest/jobs แล้วถาม AI จากข้อมูลจริง",
    steps: [
      {
        title: "อัปโหลด",
        detail: "PDF, Excel, Word ผ่าน /upload — ACL ตามโรงงาน เครื่องจักร ตำแหน่งงาน",
      },
      {
        title: "Celery ingest",
        detail: "Parse → validate → chunk → embed — 15 ประเภทเอกสารจาก YAML",
      },
      {
        title: "Dual store",
        detail: "Qdrant vectors (shard ต่อโรงงาน) + Postgres chunk mirror สำหรับ hybrid search",
      },
      {
        title: "Retrieve",
        detail: "Strict → relaxed → alias → no-data พร้อม Prometheus counters",
      },
      {
        title: "ถาม Neo Chat",
        detail: "แชทเซสชัน สรุปภาษาไทยจากคู่มืออังกฤษ verified Q&A cache",
      },
      {
        title: "ลงมือทำ",
        detail: "RCA, handover, ใบสั่งงาน, inventory insights, predictive at-risk",
      },
    ],
  },
  documents: {
    eyebrow: "Ingestion",
    title: "15 ประเภทเอกสาร —",
    titleHighlight: "กำหนดด้วย YAML",
    subtitle:
      "PDF, Excel, Word, JSON, OCR และ knowledge_document fallback — แก้ machine alias ทุกแถว",
    categories: [
      {
        name: "ความรู้",
        types: ["machine_manual", "sop", "drawing", "datasheet", "training_note", "knowledge_document"],
      },
      { name: "ซ่อมบำรุง", types: ["repair_history", "work_order"] },
      { name: "ตรวจสอบ", types: ["inspection_report", "incident_report", "near_miss"] },
      { name: "มาตรฐาน", types: ["safety_certificate", "iso_certificate"] },
      { name: "คลังอะไหล่", types: ["spare_part_catalog", "purchase_order"] },
    ],
  },
  features: {
    eyebrow: "แพลตฟอร์ม",
    title: "ทุกสิ่งที่โรงงานต้องการ —",
    titleHighlight: "ในระบบเดียว",
    subtitle: "จากช่างไลน์ถึงหัวหน้ากะและแอดมิน — ชั้นความรู้ร่วมกัน ปลอดภัยบนโครงสร้างของคุณ",
    items: [
      {
        title: "ถาม AI จากเอกสารจริง",
        description: "Hybrid RAG จากคู่มือ SOP ประวัติซ่อม — ตอบภาษาไทยพร้อมอ้างอิง",
      },
      {
        title: "ศูนย์เอกสาร",
        description: "อัปโหลด PDF/Excel ACL ตามตำแหน่งงาน ค้นหาและดูเอกสารทันที",
      },
      {
        title: "ใบสั่งงาน & เครื่องจักร",
        description: "เปิด มอบหมาย ปิด WO จัดการเครื่องจักร alias และ decommission",
      },
      {
        title: "วิเคราะห์ & handover",
        description: "แนวโน้มซ่อม สรุป downtime และการ์ดส่งมอบกะ",
      },
      {
        title: "สิทธิ์ตามโรงงาน",
        description: "อ่าน/เขียนต่อโรงงาน routing ผู้ปฏิบัติการ IAM แอดมิน — บังคับใน middleware",
      },
      {
        title: "พื้นที่แชท",
        description: "UI แบบ Gemini เซสชัน แผง RCA และ PWA รองรับออฟไลน์",
      },
    ],
  },
  deepDive: {
    eyebrow: "เจาะลึก",
    title: "สร้างจาก workflow โรงงานจริง",
    subtitle: "21 โมดูล API ที่ /api/v1 — ไม่ใช่แชทบอททั่วไป",
    tabs: [
      {
        id: "rag",
        label: "RAG & แชท",
        headline: "Hybrid retrieval พร้อม fallback 4 ระดับ",
        bullets: [
          "Qdrant vector + Postgres lexical v2 (1024-dim BAAI/bge-m3)",
          "Cross-encoder reranker — BAAI/bge-reranker-v2-m3",
          "Extract-then-paraphrase grounding แปลภาษาไทยสำหรับผู้ปฏิบัติการ",
          "Verified Q&A cache (opt-in admin verify)",
          "แชทแบบ Gemini: เซสชัน pin/rename แผง RCA SSE streaming",
        ],
        endpoint: "POST /api/v1/chat/{session}/ask",
      },
      {
        id: "analytics",
        label: "วิเคราะห์",
        headline: "ภาษาธรรมชาติบนประวัติซ่อม",
        bullets: [
          "Text-to-SQL บน repair_history — รองรับวลีเวลาภาษาไทย",
          "LLM-as-Judge + reverse verification ก่อนรัน SQL",
          "ตารางซ่อมที่ /repairs กรอง เรียง ส่งออก CSV",
          "สรุปรายเดือน downtime & ต้นทุนผ่าน analytics API",
          "43-case RAG/SQL eval baseline gate ใน CI",
        ],
        endpoint: "POST /api/v1/analytics/ask",
      },
      {
        id: "ops",
        label: "ปฏิบัติการ",
        headline: "ใบสั่งงาน handover คลัง predictive",
        bullets: [
          "Work order CRUD + มอบหมายผู้ใช้ + Excel ingest (work_order.yaml)",
          "สรุปส่งมอบกะภาษาไทยจาก WO & เหตุการณ์",
          "Inventory insights: สต็อกต่ำ dead stock แนะนำสั่งซื้อ",
          "เครื่อง at-risk จากรูปแบบซ่อม (ไม่ใช่เซ็นเซอร์สด)",
          "API เฉพาะทาง: drawings, certificates, inspections, incidents",
        ],
        endpoint: "POST /api/v1/handover/summary",
      },
      {
        id: "insights",
        label: "Insights",
        headline: "Problem Trends สำหรับหัวหน้างาน",
        bullets: [
          "Problem Pulse — อาการซ้ำข้ามเครื่อง",
          "แนวโน้มคำถาม AI — สิ่งที่ผู้ปฏิบัติการถามจริง",
          "Symptom heatmap และ feedback-gap analysis",
          "Insights hotness alerts ผ่าน SSE",
        ],
        endpoint: "GET /api/v1/insights/*",
      },
      {
        id: "security",
        label: "ความปลอดภัย",
        headline: "Factory RBAC + job-position document ACL",
        bullets: [
          "บทบาท: employee, operator, admin — middleware route guards",
          "อ่าน / เขียน / admin ต่อโรงงานทุก API",
          "Job-position ACL บนเอกสาร (QC, QA, maintenance ฯลฯ)",
          "Google OAuth + JWT; production fail-closes เมื่อไม่มี auth",
          "Admin IAM ที่ /admin — users, factories, positions",
        ],
        endpoint: "PATCH /api/v1/documents/{id}/visibility",
      },
      {
        id: "offline",
        label: "PWA & แจ้งเตือน",
        headline: "ออฟไลน์บนพื้นโรงงาน + แจ้งเตือนสด",
        bullets: [
          "PWA ติดตั้งได้ — manifest, service worker v2, ไอคอน 192/512",
          "IndexedDB PDF cache — prefetch สูงสุด 5 เอกสารต่อเครื่อง (Wi-Fi เท่านั้น)",
          "Feedback outbox sync เมื่อกลับออนไลน์",
          "SSE alert stream พร้อมการแจ้งเตือนถาวร",
          "Prometheus /metrics + Grafana spark-overview",
        ],
        endpoint: "GET /api/v1/alerts/stream",
      },
    ],
    quickLinks: [
      { label: "RCA analyze", path: "/rca/analyze" },
      { label: "Inventory", path: "/inventory/insights" },
      { label: "Alerts SSE", path: "/alerts/stream" },
      { label: "Observability", path: "/observability/overview" },
    ],
  },
  personas: {
    eyebrow: "บทบาทผู้ใช้",
    title: "เครื่องมือที่เหมาะกับทุกบทบาทบนพื้นโรงงาน",
    subtitle:
      "Middleware บังคับเส้นทาง — พนักงานอ่านอย่างเดียวเข้า /upload ไม่ได้ แม้พิมพ์ URL โดยตรง",
    homeRoute: "หน้าแรก →",
    items: [
      {
        role: "แอดมิน",
        user: "เข้าถึงโรงงานเต็มรูปแบบ",
        access: "ทุกโรงงาน (F-01, F-02) · IAM เต็มรูปแบบ",
        routes: ["/admin", "/machines", "/upload"],
        home: "/chat",
      },
      {
        role: "ผู้ปฏิบัติการ / เขียน",
        user: "สิทธิ์เขียนโรงงาน",
        access: "อัปโหลดเอกสาร เครื่องจักร WO insights",
        routes: ["/documents", "/upload", "/machines"],
        home: "/chat",
      },
      {
        role: "พนักงาน (อ่าน)",
        user: "F-01 อ่านอย่างเดียว",
        access: "F-01 อ่านอย่างเดียว · แชท & floor feedback",
        routes: ["/chat", "/feedback", "RAG + ACL docs"],
        home: "/chat",
      },
    ],
  },
  neo: {
    eyebrow: "พบ Neo Chat",
    title: "AI โรงงานของคุณ —",
    titleHighlight: "ติดตั้งได้บนพื้นโรงงาน",
    subtitle:
      "Neo Chat ทำงานบนไลน์ — แชทกับเอกสาร prefetch PDF ออฟไลน์ และส่ง feedback เมื่อคำตอบหรือเอกสารผิด",
    installTitle: "ติดตั้งเป็นแอป",
    installDesc: "manifest.json · service worker v2 · apple-touch-icon 180px",
    offlineTitle: "แคช PDF ออฟไลน์",
    offlineDesc: "สูงสุด 5 เอกสารต่อเครื่องใน IndexedDB — prefetch เฉพาะ Wi-Fi",
    feedbackTitle: "วงจร feedback บนพื้นโรงงาน",
    feedbackDesc: "ช่างแจ้งเอกสารหรือคำตอบ RAG ผิด — sync เมื่อออนไลน์",
    roiEyebrow: "6 use case ROI — ไม่บังคับ SaaS ภายนอก",
    roi: [
      { title: "ค้นหาความรู้", desc: "ถามคู่มือ & SOP ภาษาไทยพร้อมอ้างอิง" },
      { title: "ความเสี่ยงเชิงคาดการณ์", desc: "เครื่อง at-risk จาก heuristics ประวัติซ่อม" },
      { title: "ROI คลังอะไหล่", desc: "แจ้งสต็อกต่ำ สั่งซื้อ รายงาน DeepAnalyze" },
      { title: "ผู้ช่วย RCA", desc: "อาการ → สาเหตุจัดอันดับจากรูปแบบ + RAG" },
      { title: "ส่งมอบกะ", desc: "สรุปภาษาไทยจาก WO เหตุการณ์ งานซ่อม" },
      { title: "Observability", desc: "Prometheus metrics, Grafana plant overview" },
    ],
  },
  stack: {
    eyebrow: "เทคโนโลยี",
    title: "สแต็กที่พร้อมโรงงาน",
    subtitle: "ทุกอย่างรันบน localhost — Docker Compose, Ollama, Prometheus",
    items: [
      { name: "FastAPI", role: "API · Python 3.11+" },
      { name: "Next.js 14", role: "Web · React 18" },
      { name: "PostgreSQL 16", role: "Relational + chunk mirror" },
      { name: "Qdrant", role: "Vectors · per-factory shards" },
      { name: "Redis + Celery", role: "Async ingest queue" },
      { name: "Ollama", role: "LLM + BAAI/bge-m3 embeddings" },
      { name: "LangChain", role: "RAG orchestration" },
      { name: "Prometheus", role: "Metrics · /metrics" },
      { name: "Grafana", role: "spark-overview dashboard" },
      { name: "Docker Compose", role: "100% localhost deploy" },
    ],
    footnote:
      "SPARK_BULK_PROFILE=large — 5 โรงงาน · python scripts/demo_validate.py",
  },
  cta: {
    title: "พร้อมยกระดับการซ่อมบำรุง?",
    subtitle: "เข้าสู่ระบบด้วยบัญชีโรงงาน หรือเริ่มจากสภาพแวดล้อมเดโม",
    getStarted: "เริ่มต้นใช้งาน",
    signIn: "เข้าสู่ระบบ",
    footnote: "รัน ./scripts/bootstrap_demo.sh ในเครื่องเพื่อข้อมูลเดโม",
  },
  footer: {
    copyright: "Neo Chat — แชทความรู้โรงงาน AI บนเครือข่ายคุณ",
    privacy: "ความเป็นส่วนตัว",
    signIn: "เข้าสู่ระบบ",
  },
};

const landingEn: LandingMessages = {
  nav: {
    pipeline: "Pipeline",
    documents: "Documents",
    capabilities: "Capabilities",
    personas: "Personas",
    stack: "Stack",
    signIn: "Sign in",
    explore: "Explore",
    home: "Home",
    openMenu: "Open menu",
    closeMenu: "Close menu",
    switchLight: "Switch to light theme",
    switchDark: "Switch to dark theme",
    language: "Change language",
  },
  hero: {
    badgeOnPrem: "On-prem deployment — factory data stays yours",
    badgeLocal: "Demo on this device — factory data stays yours",
    titleLine1: "The future of the plant floor",
    titleLine2: "starts with shared",
    rotatingWords: ["knowledge", "repairs", "documents", "work orders", "insights"],
    subtitle:
      "Neo Chat — search manuals, ask AI, manage machines and work orders. Built for real factories, secured on your network.",
    accountNote: "Accounts are created by your plant administrator — sign in with the credentials you were given.",
    signIn: "Sign in",
    seeHow: "See how it works",
    statDocTypes: "15 doc types",
    statHybridRag: "Hybrid RAG",
    statRbac: "Factory RBAC",
    chatLines: [
      "How do I fix servo overheating on MC-001?",
      "Searching manuals + repair history…",
      "Root cause: cooling fan clogged. See SOP §4.2.",
    ],
    machines: "Machines",
    openWos: "Open WOs",
    active: "● Active",
    askNeo: "Ask Neo Chat",
    docsIndexed: "Docs indexed",
    avgAnswer: "Avg. answer",
    sample: "sample",
  },
  marquee: landingTh.marquee,
  stats: [
    { value: "15", label: "YAML document types" },
    { value: "21", label: "API modules at /api/v1" },
    { value: "4-level", label: "RAG fallback ladder" },
    { value: "43", label: "RAG/SQL eval cases in CI" },
    { value: "1024", label: "Embedding dimensions (bge-m3)" },
    { value: "100%", label: "On-premise · localhost" },
  ],
  pipeline: {
    eyebrow: "Pipeline",
    title: "From upload to action —",
    titleHighlight: "one async pipeline",
    subtitle:
      "Upload via /upload, track jobs at /api/v1/ingest/jobs, then ask AI from real indexed data.",
    steps: [
      {
        title: "Upload",
        detail: "PDF, Excel, Word via /upload — factory, machine, job-position ACL",
      },
      {
        title: "Celery ingest",
        detail: "Parse → validate → chunk → embed — 15 YAML-driven document types",
      },
      {
        title: "Dual store",
        detail: "Qdrant vectors (per-factory shards) + Postgres chunk mirror for hybrid search",
      },
      {
        title: "Retrieve",
        detail: "Strict filter → relaxed → alias → graceful no-data with Prometheus counters",
      },
      {
        title: "Ask Neo Chat",
        detail: "Chat sessions, Thai synthesis from English manuals, verified Q&A cache",
      },
      {
        title: "Act",
        detail: "RCA, handover, work orders, inventory insights, predictive at-risk",
      },
    ],
  },
  documents: {
    eyebrow: "Ingestion",
    title: "15 document types —",
    titleHighlight: "YAML-configured",
    subtitle:
      "PDF, Excel, Word, JSON, OCR, and a generic knowledge_document fallback. Machine alias resolution on every row.",
    categories: [
      {
        name: "Knowledge",
        types: ["machine_manual", "sop", "drawing", "datasheet", "training_note", "knowledge_document"],
      },
      { name: "Maintenance", types: ["repair_history", "work_order"] },
      { name: "Inspection", types: ["inspection_report", "incident_report", "near_miss"] },
      { name: "Compliance", types: ["safety_certificate", "iso_certificate"] },
      { name: "Inventory", types: ["spare_part_catalog", "purchase_order"] },
    ],
  },
  features: {
    eyebrow: "Platform",
    title: "Everything your plant floor needs —",
    titleHighlight: "in one stack",
    subtitle:
      "From line technicians to shift leads and admins — one shared knowledge layer, secured on your infrastructure.",
    items: [
      {
        title: "Ask AI from real docs",
        description: "Hybrid RAG over manuals, SOPs, and repair history — Thai answers with cited sources.",
      },
      {
        title: "Document hub",
        description: "Upload PDF/Excel, job-position ACL, instant search and viewer.",
      },
      {
        title: "Work orders & machines",
        description: "Open, assign, and close WOs. Manage machines, aliases, and decommission.",
      },
      {
        title: "Analytics & handover",
        description: "Repair trends, downtime summaries, and shift handover cards.",
      },
      {
        title: "Factory RBAC",
        description: "Read/write per factory, operator routing, admin IAM — enforced in middleware.",
      },
      {
        title: "Chat workspace",
        description: "Gemini-style UI with sessions, RCA panel, and offline-ready PWA.",
      },
    ],
  },
  deepDive: {
    eyebrow: "Deep dive",
    title: "Built from real factory workflows",
    subtitle: "21 API modules at /api/v1 — not a generic chatbot wrapper.",
    tabs: [
      {
        id: "rag",
        label: "RAG & Chat",
        headline: "Hybrid retrieval with a 4-level fallback ladder",
        bullets: [
          "Qdrant vector search + Postgres lexical v2 (1024-dim BAAI/bge-m3)",
          "Cross-encoder reranker — BAAI/bge-reranker-v2-m3",
          "Extract-then-paraphrase grounding with Thai operator translation",
          "Verified Q&A cache (opt-in admin verify)",
          "Gemini-style chat: sessions, pin/rename, RCA panel, SSE answer streaming",
        ],
        endpoint: "POST /api/v1/chat/{session}/ask",
      },
      {
        id: "analytics",
        label: "Analytics",
        headline: "Natural language over repair history",
        bullets: [
          "Text-to-SQL on partitioned repair_history — Thai temporal phrases supported",
          "LLM-as-Judge + reverse verification before executing SQL",
          "Repairs table at /repairs with filter, sort, CSV export",
          "Monthly buckets, downtime & cost summaries via analytics API",
          "43-case RAG/SQL evaluation baseline gate in CI",
        ],
        endpoint: "POST /api/v1/analytics/ask",
      },
      {
        id: "ops",
        label: "Operations",
        headline: "Work orders, handover, inventory, predictive",
        bullets: [
          "Work order CRUD + assignable users + Excel ingest (work_order.yaml)",
          "Shift handover summaries in Thai from open WOs & incidents",
          "Inventory insights: low stock, dead stock, reorder suggestions",
          "Predictive at-risk machines from repair patterns (not live sensors)",
          "Specialized APIs: drawings, certificates, inspections, incidents",
        ],
        endpoint: "POST /api/v1/handover/summary",
      },
      {
        id: "insights",
        label: "Insights",
        headline: "Problem Trends for supervisors",
        bullets: [
          "Problem Pulse — recurring symptoms across machines",
          "AI question trends — what operators actually ask",
          "Symptom heatmap and feedback-gap analysis",
          "Insights hotness alerts via SSE stream",
        ],
        endpoint: "GET /api/v1/insights/*",
      },
      {
        id: "security",
        label: "Security",
        headline: "Factory RBAC + job-position document ACL",
        bullets: [
          "Roles: employee, operator, admin — middleware route guards",
          "Per-factory read / write / admin on every API",
          "Job-position ACL on documents (QC, QA, maintenance, etc.)",
          "Google OAuth + JWT; production fail-closes on missing auth",
          "Admin IAM at /admin — users, factories, positions",
        ],
        endpoint: "PATCH /api/v1/documents/{id}/visibility",
      },
      {
        id: "offline",
        label: "PWA & Alerts",
        headline: "Floor-ready offline + live notifications",
        bullets: [
          "Installable PWA — manifest, service worker v2, 192/512 icons",
          "IndexedDB PDF cache — prefetch up to 5 docs per machine (Wi-Fi only)",
          "Feedback outbox syncs when back online",
          "SSE alert stream with persisted notifications",
          "Prometheus /metrics + Grafana spark-overview dashboard",
        ],
        endpoint: "GET /api/v1/alerts/stream",
      },
    ],
    quickLinks: landingTh.deepDive.quickLinks,
  },
  personas: {
    eyebrow: "Personas",
    title: "Right tools for every role on the floor",
    subtitle:
      "Middleware enforces routes — read-only employees cannot reach /upload even via URL. Demo seed: ./scripts/bootstrap_demo.sh",
    homeRoute: "Home route →",
    items: [
      {
        role: "Admin",
        user: "Full factory access",
        access: "All factories (F-01, F-02) · full IAM",
        routes: ["/admin", "/machines", "/upload"],
        home: "/chat",
      },
      {
        role: "Operator / Write",
        user: "factory write access",
        access: "Upload docs, machines, WOs, insights",
        routes: ["/documents", "/upload", "/machines"],
        home: "/chat",
      },
      {
        role: "Employee (read)",
        user: "F-01 read-only access",
        access: "F-01 read-only · chat & floor feedback",
        routes: ["/chat", "/feedback", "RAG + ACL docs"],
        home: "/chat",
      },
    ],
  },
  neo: {
    eyebrow: "Meet Neo Chat",
    title: "Your plant AI —",
    titleHighlight: "installable on the floor",
    subtitle:
      "Neo Chat runs on the line — chat with your docs, prefetch PDFs for offline, and submit floor feedback when answers or documents are wrong.",
    installTitle: "Install as app",
    installDesc: "manifest.json · service worker v2 · apple-touch-icon 180px",
    offlineTitle: "Offline PDF cache",
    offlineDesc: "Up to 5 documents per machine in IndexedDB — Wi-Fi only prefetch",
    feedbackTitle: "Floor feedback loop",
    feedbackDesc: "Technicians flag bad docs or RAG answers — syncs when online",
    roiEyebrow: "6 native ROI use cases — no mandatory external SaaS",
    roi: [
      { title: "Knowledge retrieval", desc: "Ask manuals & SOPs in Thai with citations" },
      { title: "Predictive risk", desc: "At-risk machines from repair history heuristics" },
      { title: "Inventory ROI", desc: "Low-stock alerts, reorder, DeepAnalyze reports" },
      { title: "RCA assistant", desc: "Symptom → ranked causes from patterns + RAG" },
      { title: "Shift handover", desc: "Thai briefing from WOs, incidents, repairs" },
      { title: "Observability", desc: "Prometheus metrics, Grafana plant overview" },
    ],
  },
  stack: {
    eyebrow: "Stack",
    title: "Production-ready stack",
    subtitle: "Everything runs on localhost — Docker Compose, Ollama, Prometheus",
    items: landingTh.stack.items,
    footnote: "SPARK_BULK_PROFILE=large — 5 factories · python scripts/demo_validate.py",
  },
  cta: {
    title: "Ready to spark smarter maintenance?",
    subtitle: "Sign in with your factory account or start with the demo environment.",
    getStarted: "Get started for free",
    signIn: "Sign in",
    footnote: "Run ./scripts/bootstrap_demo.sh locally for demo credentials.",
  },
  footer: {
    copyright: "Neo Chat — Factory knowledge chat, on-prem AI",
    privacy: "Privacy",
    signIn: "Sign in",
  },
};

const LANDING_MESSAGES: Record<Locale, LandingMessages> = {
  th: landingTh,
  en: landingEn,
};

export function getLandingMessages(locale: Locale): LandingMessages {
  return LANDING_MESSAGES[locale];
}
