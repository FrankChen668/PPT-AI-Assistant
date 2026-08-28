(function () {
  const workflowConfig = {
    prompt_deck: {
      label: "\u9010\u9875\u751f\u6210 PPT",
      detail: "\u5148\u5199\u6e05\u7b2c 1 \u9875\u8981\u8bb2\u4ec0\u4e48\uff0c\u5de5\u4f5c\u53f0\u4f1a\u81ea\u52a8\u751f\u6210\u9875\u9762\u3002",
      deckType: "single",
      pageCount: "1",
      createLabel: "\u5f00\u59cb\u9010\u9875\u751f\u6210",
      prompt: "",
    },

    // Backward-compatible aliases kept for existing tasks/sessions.
    single_page: {
      label: "\u9010\u9875\u751f\u6210 PPT",
      detail: "\u5148\u5199\u6e05\u7b2c 1 \u9875\u8981\u8bb2\u4ec0\u4e48\uff0c\u5de5\u4f5c\u53f0\u4f1a\u81ea\u52a8\u751f\u6210\u9875\u9762\u3002",
      deckType: "single",
      pageCount: "1",
      createLabel: "\u5f00\u59cb\u9010\u9875\u751f\u6210",
      prompt: "",
    },
    document_deck: {
      label: "\u6587\u6863\u8f93\u5165",
      detail: "\u4e0a\u4f20\u6216\u7c98\u8d34\u6587\u6863\uff0c\u518d\u8bf4\u660e\u60f3\u751f\u6210\u4ec0\u4e48 PPT\u3002",
      deckType: "multi",
      pageCount: "10",
      createLabel: "\u5f00\u59cb\u6587\u6863\u751f\u6210",
      prompt: "",
      sourcePlaceholder: "\u7c98\u8d34\u6587\u6863\u5185\u5bb9\uff0c\u6216\u6bcf\u884c\u586b\u5199\u4e00\u4e2a\u6587\u6863\u8def\u5f84 / URL\u3002",
    },
    optimize_existing: {
      label: "\u7ee7\u7eed\u5904\u7406\u5df2\u6709\u9879\u76ee",
      detail: "\u6253\u5f00\u4efb\u52a1\u540e\u9010\u9875\u4f18\u5316\u3002",
      deckType: "single",
      pageCount: "1",
      createLabel: "\u6253\u5f00\u4efb\u52a1\u4e2d\u5fc3",
      prompt: "\u8bf7\u5148\u5728\u5de6\u4fa7\u4efb\u52a1\u5217\u8868\u4e2d\u9009\u62e9\u8981\u7ee7\u7eed\u5904\u7406\u7684\u9879\u76ee\u3002",
    },
    deep_replica: {
      label: "\u6df1\u5ea6\u590d\u523b\uff08\u540e\u7eed\u63a5\u5165\uff09",
      detail: "\u6682\u672a\u5f00\u653e\u3002",
      deckType: "single",
      pageCount: "1",
      createLabel: "\u540e\u7eed\u63a5\u5165",
      disabledCreate: true,
      prompt: "\u6df1\u5ea6\u590d\u523b\u529f\u80fd\u540e\u7eed\u63a5\u5165\uff0c\u672c\u9636\u6bb5\u8bf7\u4f7f\u7528\u9010\u9875\u751f\u6210\u3002",
    },
    repair_existing: {
      label: "\u7ee7\u7eed\u5904\u7406\u5df2\u6709\u9879\u76ee",
      detail: "\u4e0d\u65b0\u5efa\u4efb\u52a1\uff0c\u76f4\u63a5\u8fdb\u5165\u5f53\u524d\u9879\u76ee\u5904\u7406\u3002",
      deckType: "single",
      pageCount: "1",
      createLabel: "\u8bf7\u5728\u4efb\u52a1\u4e2d\u7ee7\u7eed",
      disabledCreate: true,
      prompt: "\u8bf7\u5148\u9009\u62e9\u5df2\u6709\u4efb\u52a1\uff0c\u7136\u540e\u6309\u5f53\u524d\u9875\u72b6\u6001\u7ee7\u7eed\u5904\u7406\u3002",
    },
  };

  const slideStateText = {
    waiting_codex: "\u7b49\u5f85\u751f\u6210",
    generating: "\u6b63\u5728\u751f\u6210",
    svg_ready: "\u5df2\u751f\u6210",
    svg_missing: "\u9875\u9762\u672a\u751f\u6210",
    svg_authored: "\u5df2\u751f\u6210",
    packet_missing: "\u4efb\u52a1\u5305\u672a\u751f\u6210",
    packet_ready: "\u4efb\u52a1\u5305\u5df2\u751f\u6210",
    qa_running: "\u751f\u6210\u4e2d",
    qa_passed: "\u5df2\u751f\u6210",
    qa_failed: "\u751f\u6210\u5931\u8d25",
    regenerate_requested: "\u7b49\u5f85\u91cd\u65b0\u751f\u6210",
    restored: "\u5df2\u56de\u6eda",
  };

  const pageTypeLabels = {
    content: "\u5185\u5bb9\u9875",
    cover: "\u5c01\u9762",
    toc: "\u76ee\u5f55\u9875",
    section: "\u7ae0\u8282\u9875",
  };

  const projectStateText = {
    missing: "\u9879\u76ee\u7f3a\u5931",
    project_created: "\u5df2\u521b\u5efa",
    waiting_codex: "\u7b49\u5f85\u9875\u9762\u751f\u6210",
    generating: "\u6b63\u5728\u751f\u6210\u9875\u9762",
    svg_partial: "\u90e8\u5206\u5df2\u751f\u6210",
    svg_ready: "\u5df2\u751f\u6210",
    qa_running: "\u751f\u6210\u4e2d",
    qa_passed: "\u5df2\u751f\u6210",
    qa_failed: "\u751f\u6210\u5931\u8d25",
    export_ready: "\u5df2\u751f\u6210",
    export_running: "\u6b63\u5728\u751f\u6210 PPT",
    exported: "PPT \u5df2\u751f\u6210",
    export_review_required: "\u5df2\u751f\u6210",
    export_failed: "\u751f\u6210\u5931\u8d25",
  };

  window.WorkbenchConfig = {
    workflowConfig,
    slideStateText,
    pageTypeLabels,
    projectStateText,
  };
})();
