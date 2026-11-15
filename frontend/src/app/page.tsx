"use client";

import React, { useState, useEffect } from "react";
import {
  Bot,
  Play,
  RotateCcw,
  ShieldCheck,
  Zap,
  Terminal,
  Activity,
  UserCheck,
  SlidersHorizontal,
  FileCode,
  Layers,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Clock,
  Sparkles,
  ExternalLink,
  Laptop,
  Coins,
  Cpu,
  Lock,
  Eye,
  RefreshCw,
  Search,
  KeyRound,
  Database
} from "lucide-react";

interface Capability {
  id: string;
  title: string;
  description: string;
  risk: "READ" | "REVERSIBLE_WRITE" | "RISKY_WRITE";
  stepsCount: number;
  avgLatency: string;
  modelCalls: number;
  lastRun: string;
  yamlContent: string;
}

export default function ZimamDashboard() {
  const [activeTab, setActiveTab] = useState<"studio" | "capabilities" | "operator" | "analytics">("studio");
  const [selectedCapability, setSelectedCapability] = useState<string>("lookup_savings_balance");
  const [memberId, setMemberId] = useState<string>("10001");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [executionLogs, setExecutionLogs] = useState<string[]>([]);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [activeStep, setActiveStep] = useState<number>(0);
  const [operatorLease, setOperatorLease] = useState<"AUTOMATION" | "HUMAN">("AUTOMATION");
  const [interventionTriggered, setInterventionTriggered] = useState<boolean>(false);

  // Available capabilities
  const capabilities: Capability[] = [
    {
      id: "lookup_savings_balance",
      title: "استعلام رصيد حساب العضو (Lookup Balance)",
      description: "استكشاف نموذج البحث المصرفي واستخراج الرصيد والاسم بدقة عالية مع معالجة سيناريو الحساب غير الموجود.",
      risk: "READ",
      stepsCount: 3,
      avgLatency: "680ms",
      modelCalls: 0,
      lastRun: "منذ دقيقتين",
      yamlContent: `capability_id: lookup_savings_balance
version: 1.0.0
risk_level: READ
target_domain: "portal.bank-meridian.sa"
inputs:
  - name: member_id
    type: string
    required: true
outputs:
  - name: savings_balance
    type: money
    required: true
  - name: member_name
    type: string
    required: true
steps:
  - step_id: s1
    effect: READ
    action: click
    target:
      role: link
      accessible_name: "البحث عن الأعضاء"
  - step_id: s2
    effect: READ
    action: type
    target:
      role: textbox
      accessible_name: "رقم العضو / الحساب"
      frame: member-search-frame
    value_source: "input:member_id"
  - step_id: s3
    effect: READ
    action: click
    target:
      role: button
      accessible_name: "استعلام فوري"
final_checkpoint:
  mode: all
  predicates:
    - kind: text_present
      text: "الرصيد المتاح"
known_outcomes:
  - code: MEMBER_NOT_FOUND
    detect_text: "رقم العضو غير مسجل"
policy:
  enforce_origin: true
  prevent_mutation: true`
    },
    {
      id: "payroll_reconciliation",
      title: "مطابقة كشوفات الرواتب والتسوية (Payroll Reconciliation)",
      description: "استخراج كشوفات مسيرات الرواتب القديمة ومطابقتها حتمياً وتصدير بيانات الحسابات المعتمدة.",
      risk: "READ",
      stepsCount: 5,
      avgLatency: "940ms",
      modelCalls: 0,
      lastRun: "منذ 15 دقيقة",
      yamlContent: `capability_id: payroll_reconciliation
version: 2.1.0
risk_level: READ
target_domain: "erp.enterprise.gov.sa"
inputs:
  - name: fiscal_month
    type: string
    required: true
outputs:
  - name: total_salaries
    type: money
  - name: audited_records
    type: integer
steps:
  - step_id: p1
    action: navigate
    route: "/finance/payroll/archive"
  - step_id: p2
    action: select_option
    target: { role: combobox, accessible_name: "الشهر المالي" }
    value_source: "input:fiscal_month"
  - step_id: p3
    action: click
    target: { role: button, accessible_name: "توليد كشف المطابقة" }
final_checkpoint:
  predicates:
    - kind: element_visible
      selector: "#reconciliation-summary"`
    },
    {
      id: "update_contact_profile",
      title: "تحديث بيانات الاتصال المصرفية (Update Contact)",
      description: "تعديل رقم الجوال والعنوان الوطني في النظام البنكي القديم مع التحقق من نافذة رمز التحقق OTP.",
      risk: "REVERSIBLE_WRITE",
      stepsCount: 4,
      avgLatency: "1150ms",
      modelCalls: 0,
      lastRun: "منذ ساعة",
      yamlContent: `capability_id: update_contact_profile
version: 1.0.0
risk_level: REVERSIBLE_WRITE
target_domain: "portal.bank-meridian.sa"
inputs:
  - name: member_id
    type: string
  - name: new_phone
    type: string
steps:
  - step_id: u1
    action: type
    target: { role: textbox, accessible_name: "رقم الجوال الجديد" }
    value_source: "input:new_phone"
  - step_id: u2
    action: click
    target: { role: button, accessible_name: "حفظ وتأكيد" }
human_intervention_rules:
  - trigger_on: "OTP_DIALOG_DETECTED"
    action: "PAUSE_AND_HANDOFF_TO_OPERATOR"`
    }
  ];

  // Run Replay Simulation
  const handleRunReplay = () => {
    setIsRunning(true);
    setExecutionLogs([]);
    setExecutionResult(null);
    setActiveStep(1);

    const logs: string[] = [];
    const addLog = (msg: string) => {
      logs.push(msg);
      setExecutionLogs([...logs]);
    };

    setTimeout(() => {
      addLog("🚀 [تهيئة المحرك] بدء التنفيذ الحتمي (Deterministic Replay Engine v1.0)...");
      addLog(`📋 [ملف القدرة المعتمد] تحميل lookup_savings_balance.v1.yaml | النطاق: portal.bank-meridian.sa`);
      setActiveStep(1);
    }, 200);

    setTimeout(() => {
      addLog("🛡️ [محرك الأمان PolicyEngine] التحقق من سياسة النطاق والصلاحيات: فئة READ مسموحة بالكامل.");
      addLog("🌐 [Playwright Chromium] جلب السياق المستقل وتهيئة شاشة التفاعل الدلالية...");
      setActiveStep(2);
    }, 450);

    setTimeout(() => {
      addLog(`🎯 [مطابقة العناصر الدلالية TargetResolver] العثور على العنصر role="textbox", accessible_name="رقم العضو / الحساب" خلال 18ms`);
      addLog(`⌨️ [تنفيذ الإجراء الحتمي] إدخال رقم العضو الممرر: "${memberId}" بدون أي استدعاء خارجي للـ LLM.`);
      setActiveStep(3);
    }, 700);

    setTimeout(() => {
      addLog(`🔘 [النقر على الزر] النقر على الزر الدلالي role="button", accessible_name="استعلام فوري"`);
      addLog(`🔍 [التحقق من نقاط الفحص Checkpoint] مطابقة شرط text_present("الرصيد المتاح") -> متحقق بنجاح!`);
      setActiveStep(4);
    }, 950);

    setTimeout(() => {
      if (memberId === "10001") {
        addLog("✅ [اكتملت المهمة بنجاح] استخراج البيانات المنظمة بتوافق كامل!");
        addLog("⚡ [تقرير الاستهلاك] استدعاءات نماذج الذكاء (Model Calls): 0 توكنز | زمن التنفيذ الإجمالي: 698ms");
        setExecutionResult({
          status: "success",
          outputs: {
            member_name: "م. عبد العزيز بن سلطان المقرن",
            savings_balance: "128,450.00 ر.س",
            account_status: "نشط ومعتمد",
            account_tier: "الفئة البلاتينية المؤسسية"
          },
          metrics: {
            latency: "698ms",
            modelCalls: 0,
            tokenCost: "$0.0000",
            tokensSaved: "4,250 tokens",
            checkpointsPassed: "2 / 2"
          }
        });
      } else {
        addLog("⚠️ [نتيجة أعمال محددة مسبقاً] تم اكتشاف كود: MEMBER_NOT_FOUND (العضو غير مسجل)");
        setExecutionResult({
          status: "business_outcome",
          code: "MEMBER_NOT_FOUND",
          message: "رقم العضو غير موجود في السجلات المصرفية الحالية.",
          metrics: {
            latency: "640ms",
            modelCalls: 0,
            tokenCost: "$0.0000",
            tokensSaved: "3,800 tokens"
          }
        });
      }
      setIsRunning(false);
    }, 1200);
  };

  // Trigger Human Intervention Simulation
  const handleSimulateIntervention = () => {
    setInterventionTriggered(true);
    setOperatorLease("HUMAN");
  };

  const handleResolveIntervention = () => {
    setInterventionTriggered(false);
    setOperatorLease("AUTOMATION");
  };

  const currentCap = capabilities.find(c => c.id === selectedCapability) || capabilities[0];

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col font-thmanyah selection:bg-amber-500 selection:text-black">
      {/* Top Enterprise Banner */}
      <header className="border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md sticky top-0 z-50 px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-violet-600 flex items-center justify-center shadow-lg shadow-amber-500/25">
              <Bot className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                  زِمَام الذكي
                  <span className="text-xs font-mono uppercase px-2.5 py-0.5 rounded-full bg-amber-950/80 text-amber-400 border border-amber-800/80 shadow-sm">
                    Zimam-AI v1.2
                  </span>
                </h1>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                المنظومة الذاتية لأتمتة الأنظمة وتطبيقات الويب بحواسيب الذكاء الاصطناعي والاستدلال الحتمي
              </p>
            </div>
          </div>

          {/* Quick Metrics Badges */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-950/40 border border-amber-800/70 text-amber-300 text-xs shadow-sm">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span>التشغيل الحتمي: <strong>0 توكنز</strong></span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-violet-950/40 border border-violet-800/70 text-violet-300 text-xs shadow-sm">
              <Clock className="w-3.5 h-3.5 text-violet-400" />
              <span>متوسط السرعة: <strong>~700ms</strong></span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-300 text-xs">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              <span>سياسة الأمان: <strong>صارمة ومطابقة</strong></span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto mt-4 pt-2 border-t border-slate-800/60 flex items-center gap-2 overflow-x-auto">
          <button
            onClick={() => setActiveTab("studio")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "studio"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Laptop className="w-4 h-4" />
            لوحة العمليات والاستكشاف الحي
          </button>
          <button
            onClick={() => setActiveTab("capabilities")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "capabilities"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <FileCode className="w-4 h-4" />
            مستودع القدرات المترجمة (YAML)
          </button>
          <button
            onClick={() => setActiveTab("operator")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "operator"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <UserCheck className="w-4 h-4" />
            مركز التدخل البشري والتحكم
            {interventionTriggered && (
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("analytics")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "analytics"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Activity className="w-4 h-4" />
            المؤشرات المالية والتوفير (ROI)
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">

        {/* TAB 1: LIVE STUDIO */}
        {activeTab === "studio" && (
          <div className="space-y-6">
            {/* Control Strip */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Configuration Card */}
              <div className="lg:col-span-1 bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <h2 className="font-bold text-base text-white flex items-center gap-2">
                    <SlidersHorizontal className="w-4 h-4 text-indigo-400" />
                    إعدادات التشغيل الحتمي
                  </h2>
                  <span className="text-xs bg-emerald-950 text-emerald-400 px-2 py-0.5 rounded border border-emerald-800/80">
                    Model Calls = 0
                  </span>
                </div>

                <div>
                  <label className="text-xs text-slate-400 block mb-1.5 font-medium">القدرة المؤتمتة (Capability):</label>
                  <select
                    value={selectedCapability}
                    onChange={(e) => setSelectedCapability(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  >
                    {capabilities.map((c) => (
                      <option key={c.id} value={c.id}>{c.title}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs text-slate-400 block mb-1.5 font-medium">معامل الإدخال (Member ID / Input):</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={memberId}
                      onChange={(e) => setMemberId(e.target.value)}
                      placeholder="10001"
                      className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                    />
                    <button
                      onClick={() => setMemberId("10001")}
                      className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-2 rounded-xl transition-all"
                    >
                      عضو موجود
                    </button>
                    <button
                      onClick={() => setMemberId("99999")}
                      className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-2 rounded-xl transition-all"
                    >
                      غير موجود
                    </button>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 text-xs space-y-2">
                  <div className="flex justify-between text-slate-400">
                    <span>مستوى الخطورة (Risk):</span>
                    <span className="font-mono text-emerald-400 font-bold">{currentCap.risk}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>عدد الخطوات الحتمية:</span>
                    <span className="font-mono text-slate-200">{currentCap.stepsCount} خطوات</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>المتوسط الزمني المقاس:</span>
                    <span className="font-mono text-indigo-400">{currentCap.avgLatency}</span>
                  </div>
                </div>

                <div className="space-y-2 pt-2">
                  <button
                    onClick={handleRunReplay}
                    disabled={isRunning}
                    className="w-full py-3 px-4 rounded-xl font-bold text-sm bg-gradient-to-r from-emerald-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 text-white shadow-lg shadow-emerald-900/30 flex items-center justify-center gap-2 transition-all disabled:opacity-50"
                  >
                    {isRunning ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        جارٍ التنفيذ الحتمي السريع...
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4 fill-white" />
                        تشغيل حتمي فوري (Replay)
                      </>
                    )}
                  </button>

                  <button
                    onClick={handleSimulateIntervention}
                    className="w-full py-2 px-3 rounded-xl text-xs bg-amber-950/40 hover:bg-amber-900/40 text-amber-400 border border-amber-800/60 flex items-center justify-center gap-1.5 transition-all"
                  >
                    <AlertCircle className="w-3.5 h-3.5" />
                    محاكاة طلب تدخل بشري (Human Intervention)
                  </button>
                </div>
              </div>

              {/* Live Interactive Browser Surface */}
              <div className="lg:col-span-2 bg-slate-900/70 border border-slate-800 rounded-2xl flex flex-col overflow-hidden">
                {/* Browser Mock Header */}
                <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-rose-500"></div>
                    <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                    <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
                    <span className="text-xs font-mono text-slate-400 mr-2">
                      https://portal.bank-meridian.sa/pine-valley/members
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-400 border border-indigo-800 font-mono">
                      Playwright Active
                    </span>
                  </div>
                </div>

                {/* Simulated Portal Content */}
                <div className="p-6 flex-1 bg-slate-950 flex flex-col justify-center relative overflow-hidden">
                  {/* Visual Stepper Indicators */}
                  <div className="grid grid-cols-4 gap-2 mb-6">
                    {["1. استكشاف المسار", "2. التحقق من السياسة", "3. استهداف العنصر", "4. التحقق والإنهاء"].map((title, idx) => (
                      <div
                        key={idx}
                        className={`p-2 rounded-lg text-center text-xs font-medium border transition-all ${
                          activeStep > idx
                            ? "bg-emerald-950/60 border-emerald-800 text-emerald-400"
                            : activeStep === idx + 1
                            ? "bg-indigo-950 border-indigo-700 text-indigo-300 animate-pulse"
                            : "bg-slate-900/40 border-slate-800/80 text-slate-500"
                        }`}
                      >
                        {title}
                      </div>
                    ))}
                  </div>

                  {/* Mock Portal Form Window */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl max-w-xl mx-auto w-full relative">
                    {/* Semantic Target Highlight Box when running */}
                    {activeStep === 3 && (
                      <div className="absolute inset-0 border-2 border-indigo-500 rounded-xl pointer-events-none animate-pulse bg-indigo-500/5 flex items-start justify-end p-2">
                        <span className="text-[10px] font-mono bg-indigo-600 text-white px-2 py-0.5 rounded shadow">
                          Semantic Locator: role=textbox, name=&quot;Member ID&quot;
                        </span>
                      </div>
                    )}

                    <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
                      <div>
                        <h3 className="font-bold text-white text-base">منظومة ميريديان المصرفية | بوابة الفروع</h3>
                        <p className="text-xs text-slate-400">نظام إدارة وخدمة حسابات العملاء القديم (Legacy Core Banking)</p>
                      </div>
                      <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-300 font-mono">
                        Tenant: Pine Valley
                      </span>
                    </div>

                    <div className="space-y-4">
                      <div>
                        <label className="text-xs text-slate-300 block mb-1">رقم الحساب / العضو (Member Number):</label>
                        <div className="relative">
                          <input
                            type="text"
                            readOnly
                            value={memberId}
                            className={`w-full bg-slate-950 border rounded-lg px-3 py-2 text-sm font-mono transition-all ${
                              activeStep === 3
                                ? "border-indigo-500 ring-2 ring-indigo-500/30 text-indigo-300"
                                : "border-slate-700 text-slate-200"
                            }`}
                          />
                          <span className="absolute left-3 top-2.5 text-xs text-slate-500 font-mono">
                            #frame: member-search
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-end gap-3 pt-2">
                        <button
                          disabled
                          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                            activeStep === 4
                              ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/30"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          استعلام فوري عن الرصيد
                        </button>
                      </div>
                    </div>

                    {/* Output Card */}
                    {executionResult && (
                      <div className={`mt-5 p-4 rounded-xl border animate-in fade-in duration-300 ${
                        executionResult.status === "success"
                          ? "bg-emerald-950/30 border-emerald-800/80 text-emerald-200"
                          : "bg-amber-950/30 border-amber-800/80 text-amber-200"
                      }`}>
                        {executionResult.status === "success" ? (
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold flex items-center gap-1.5 text-emerald-400">
                                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                تم استخراج النتيجة الحتمية بنجاح
                              </span>
                              <span className="text-[11px] font-mono bg-emerald-900/60 px-2 py-0.5 rounded text-emerald-300">
                                Model Calls: 0
                              </span>
                            </div>
                            <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
                              <div>
                                <span className="text-slate-400 block text-[11px]">اسم العضو:</span>
                                <strong className="text-white text-sm">{executionResult.outputs.member_name}</strong>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[11px]">الرصيد المتاح:</span>
                                <strong className="text-emerald-400 text-sm font-mono">{executionResult.outputs.savings_balance}</strong>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-xs">
                            <AlertCircle className="w-4 h-4 text-amber-400" />
                            <span>{executionResult.message} ({executionResult.code})</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Execution Terminal / Trace Logs */}
            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 font-mono text-xs overflow-hidden">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-slate-400">
                <span className="flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-emerald-400" />
                  سجل التتبع اللحظي لمحرك التشغيل (Execution Trace Stream)
                </span>
                <span className="text-[11px] text-slate-500">Playwright CDP Session: Active</span>
              </div>
              <div className="mt-3 space-y-1.5 max-h-48 overflow-y-auto">
                {executionLogs.length === 0 ? (
                  <p className="text-slate-600 italic">اضغط على &quot;تشغيل حتمي فوري&quot; لمعاينة تدفق العمليات الحتمية بدون استدعاءات نماذج...</p>
                ) : (
                  executionLogs.map((log, i) => (
                    <div key={i} className="text-slate-300 leading-relaxed">
                      {log}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: CAPABILITIES HUB */}
        {activeTab === "capabilities" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {capabilities.map((cap) => (
                <div
                  key={cap.id}
                  onClick={() => setSelectedCapability(cap.id)}
                  className={`p-5 rounded-2xl border cursor-pointer transition-all ${
                    selectedCapability === cap.id
                      ? "bg-slate-900 border-indigo-500 shadow-xl shadow-indigo-950/50"
                      : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs px-2.5 py-0.5 rounded font-mono font-bold bg-slate-800 text-slate-300">
                      {cap.risk}
                    </span>
                    <span className="text-xs text-emerald-400 font-mono">
                      {cap.avgLatency}
                    </span>
                  </div>
                  <h3 className="font-bold text-white text-base mb-1.5">{cap.title}</h3>
                  <p className="text-xs text-slate-400 leading-relaxed mb-4">{cap.description}</p>
                  <div className="flex items-center justify-between pt-3 border-t border-slate-800 text-[11px] text-slate-500 font-mono">
                    <span>{cap.stepsCount} خطوات مجمعة</span>
                    <span>استدعاءات: 0 توكن</span>
                  </div>
                </div>
              ))}
            </div>

            {/* YAML Capability Artifact Viewer */}
            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-6">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
                <div>
                  <h3 className="font-bold text-white text-base flex items-center gap-2">
                    <FileCode className="w-5 h-5 text-indigo-400" />
                    ملف القدرة المترجم: {currentCap.id}.v1.yaml
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    مستند حتمي مكتمل المواصفات يُنفذ بدون نموذج ذكاء اصطناعي (Model-Free Capability Artifact)
                  </p>
                </div>
                <div className="flex gap-2">
                  <span className="text-xs bg-indigo-950 text-indigo-400 border border-indigo-800 px-3 py-1 rounded-lg font-mono">
                    Deterministic Schema v1.0
                  </span>
                </div>
              </div>

              <pre className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 text-xs font-mono text-emerald-300 overflow-x-auto leading-relaxed">
                {currentCap.yamlContent}
              </pre>
            </div>
          </div>
        )}

        {/* TAB 3: HUMAN OPERATOR CONSOLE */}
        {activeTab === "operator" && (
          <div className="space-y-6">
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
              <div className="flex flex-col md:flex-row items-center justify-between gap-4 pb-6 border-b border-slate-800">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <UserCheck className="w-5 h-5 text-amber-400" />
                    مركز التدخل البشري الفوري (Human-in-the-Loop Takeover)
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    إدارة انتقال التحكم التلقائي بين الأتمتة والمشغل البشري في حالات الـ OTP والنوافذ المجهولة
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-left font-mono text-xs">
                    <span className="text-slate-400 block">حالة الملكية (Lease Owner):</span>
                    <strong className={operatorLease === "HUMAN" ? "text-amber-400" : "text-emerald-400"}>
                      {operatorLease === "HUMAN" ? "المشغل البشري (HUMAN)" : "الوكيل الحتمي (AUTOMATION)"}
                    </strong>
                  </div>
                  {operatorLease === "HUMAN" ? (
                    <button
                      onClick={handleResolveIntervention}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-emerald-900/30"
                    >
                      إعادة التفويض للوكيل
                    </button>
                  ) : (
                    <button
                      onClick={handleSimulateIntervention}
                      className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-amber-900/30"
                    >
                      استلام التحكم اليدوي
                    </button>
                  )}
                </div>
              </div>

              {/* State Representation */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-xs text-slate-400 block mb-1">نافذة التدخل النشطة:</span>
                  <strong className="text-white text-sm">
                    {interventionTriggered ? "رمز التحقق الثنائي (OTP_REQUIRED)" : "لا توجد تدابير معلقة"}
                  </strong>
                </div>
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-xs text-slate-400 block mb-1">جلسة المتصفح المشتركة:</span>
                  <strong className="text-emerald-400 text-sm font-mono">Chromium #8765-Isolated</strong>
                </div>
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-xs text-slate-400 block mb-1">مستوى الأمان وضمان الحفظ:</span>
                  <strong className="text-blue-400 text-sm">معتمد ومشفر (Monotonic Lease)</strong>
                </div>
              </div>

              {interventionTriggered && (
                <div className="mt-6 p-5 rounded-2xl bg-amber-950/30 border border-amber-800/80 animate-in fade-in">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                    <div className="space-y-3 flex-1">
                      <div>
                        <h4 className="font-bold text-amber-300 text-sm">تم إيقاف الأتمتة مؤقتاً: مطلوب إدخال رمز التحقق (OTP)</h4>
                        <p className="text-xs text-slate-300 mt-1">
                          رصد محرك الأمان نافذة تتطلب إدخال رمز التحقق المرسل للجوال. تم نقل التحكم إليك لحماية سرية البيانات.
                        </p>
                      </div>

                      <div className="flex items-center gap-3">
                        <input
                          type="text"
                          placeholder="أدخل رمز التحقق (4 أرقام)..."
                          className="bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-white max-w-xs focus:outline-none focus:border-amber-500"
                        />
                        <button
                          onClick={handleResolveIntervention}
                          className="px-4 py-2 rounded-xl text-xs font-bold bg-amber-600 hover:bg-amber-500 text-white transition-all"
                        >
                          تأكيد الرمز واستئناف الأتمتة
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: EXECUTIVE ROI & ANALYTICS */}
        {activeTab === "analytics" && (
          <div className="space-y-6">
            {/* Top 4 KPI Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-400">إجمالي العمليات المنفذة</span>
                  <Bot className="w-4 h-4 text-indigo-400" />
                </div>
                <div className="text-2xl font-bold font-mono text-white">1,420</div>
                <p className="text-[11px] text-emerald-400 mt-1">↑ 100% نجاح حتمي</p>
              </div>

              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-400">التوفير المالي في التوكنز</span>
                  <Coins className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="text-2xl font-bold font-mono text-emerald-400">$5,320+</div>
                <p className="text-[11px] text-slate-400 mt-1">مقارنة باستدعاءات VLM التقليدية</p>
              </div>

              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-400">متوسط سرعة الإنجاز</span>
                  <Clock className="w-4 h-4 text-blue-400" />
                </div>
                <div className="text-2xl font-bold font-mono text-blue-400">716 ms</div>
                <p className="text-[11px] text-blue-300 mt-1">أسرع بـ 15 ضعفاً من الـ LLMs</p>
              </div>

              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-400">الاستدعاءات في مرحلة التشغيل</span>
                  <Zap className="w-4 h-4 text-amber-400" />
                </div>
                <div className="text-2xl font-bold font-mono text-amber-400">0 Tokens</div>
                <p className="text-[11px] text-amber-300 mt-1">تكلفة تشغيلية = صفر</p>
              </div>
            </div>

            {/* Comparison Table */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
              <h3 className="font-bold text-white text-base mb-4">
                المقارنة الهندسية: وكلاء الشاشة التقليديون vs منظومة «زِمَام الذكي»
              </h3>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-right">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-3 px-4">المعيار التقني</th>
                      <th className="py-3 px-4">وكلاء الشاشة التقليديون (Raw VLM)</th>
                      <th className="py-3 px-4 text-emerald-400 font-bold">منظومة «زِمَام الذكي» الحتمية</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    <tr>
                      <td className="py-3 px-4 font-medium text-white">تكلفة التوكنز في كل عملية</td>
                      <td className="py-3 px-4 text-rose-400 font-mono">~3,500 إلى 15,000 توكنز في كل نقرة</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold font-mono">0 توكنز (مجاني بالكامل)</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-medium text-white">زمن التنفيذ لكل خطوة</td>
                      <td className="py-3 px-4 text-amber-400 font-mono">3,000ms - 8,000ms</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold font-mono">~716ms (سرعة قياسية)</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-medium text-white">نسبة الموثوقية والهلوسة</td>
                      <td className="py-3 px-4 text-rose-400">معرضة لهلوسة الإحداثيات والخطأ</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold">حتمية 100% مع نقاط فحص Checkpoints</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-medium text-white">التدخل البشري اللحظي</td>
                      <td className="py-3 px-4 text-slate-500">انهيار الجلسة عند مواجهة كابتشا/OTP</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold">تسليم سلس دون فقدان جلسة المتصفح</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* Enterprise Footer */}
      <footer className="border-t border-slate-800 py-6 px-6 bg-slate-950 text-center text-xs text-slate-500">
        <p>
          منظومة «زِمَام الذكي | Zimam-AI» — بيئة تشغيل حتمية لحواسيب الذكاء الاصطناعي وأتمتة الأنظمة القديمة
        </p>
        <p className="mt-1 text-slate-600 font-mono">
          هندسة وتطوير: مناف البناء (Manaf Albana) © 2026 • مرخص تحت رخصة MIT
        </p>
      </footer>
    </div>
  );
}
