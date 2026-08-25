(function () {
  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch {
      return fallback;
    }
  }

  function writeJson(key, payload) {
    try {
      localStorage.setItem(key, JSON.stringify(payload));
    } catch {
      // Ignore storage errors in private/limited browser modes.
    }
  }

  function readText(key, fallback = "") {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : raw;
    } catch {
      return fallback;
    }
  }

  function writeText(key, value) {
    try {
      localStorage.setItem(key, String(value ?? ""));
    } catch {
      // Ignore storage errors in private/limited browser modes.
    }
  }

  window.WorkbenchStateStorage = {
    readJson,
    writeJson,
    readText,
    writeText,
  };
})();
