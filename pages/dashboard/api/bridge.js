export function withTimeout(promise, timeoutMs, message) {
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = window.setTimeout(() => reject(new Error(message)), timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => window.clearTimeout(timeoutId));
}

export function normalizeBridgeResult(result) {
  if (result && typeof result === "object" && Object.prototype.hasOwnProperty.call(result, "ok")) {
    if (!result.ok) {
      throw new Error(result.error?.message || result.message || "请求失败");
    }
    return result.data || {};
  }
  return result || {};
}

function bridgeErrorMessage(error) {
  const payload = error?.response?.data || error?.data || error?.cause?.response?.data;
  return payload?.error?.message || payload?.message || error?.message || "请求失败";
}

async function bridgeRequest(promise) {
  try {
    return await promise;
  } catch (error) {
    throw new Error(bridgeErrorMessage(error), { cause: error });
  }
}

export function createDashboardApi(bridge, requestTimeoutMs) {
  async function apiGet(endpoint, params = {}, timeoutMs = requestTimeoutMs) {
    const result = await withTimeout(
      bridgeRequest(bridge.apiGet(endpoint, params)),
      timeoutMs,
      "请求超时"
    );
    return normalizeBridgeResult(result);
  }

  async function apiPost(endpoint, body = {}, timeoutMs = requestTimeoutMs) {
    const result = await withTimeout(
      bridgeRequest(bridge.apiPost(endpoint, body)),
      timeoutMs,
      "请求超时"
    );
    return normalizeBridgeResult(result);
  }

  return { apiGet, apiPost };
}
