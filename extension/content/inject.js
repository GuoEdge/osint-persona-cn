(function () {
  const CAPTURE = [
    /bilibili\.com\/x\/space\/like\/video/i,
    /bilibili\.com\/x\/space\/coin\/video/i,
    /bilibili\.com\/x\/web-interface\/history/i,
    /bilibili\.com\/x\/v3\/fav\//i,
    /bilibili\.com\/x\/v2\/medialist/i,
    /bilibili\.com\/fav\/resource\/list/i,
    /bilibili\.com\/x\/v2\/reply\/(wbi\/)?main/i,
    /bilibili\.com\/x\/v2\/reply/i,
    /bilibili\.com\/x\/relation\/followings/i,
    /bilibili\.com\/x\/web-interface\/wbi\/search/i,
    /bilibili\.com\/x\/web-interface\/search/i,
    /bilibili\.com\/x\/web-interface\/wbi\/like/i,
    /zhihu\.com\/api\/v4\/search_v3/i,
    /zhihu\.com\/api\/v4\/.*collections.*items/i,
    /zhihu\.com\/api\/v4\/.*voteanswers/i,
    /zhihu\.com\/api\/v4\/.*vote_answers/i,
    /zhihu\.com\/api\/v4\/members\/.*\/activities/i,
    /zhihu\.com\/api\/v4\/members\/.*\/followees/i,
    /zhihu\.com\/api\/v4\/.*footprints/i,
    /zhihu\.com\/api\/v4\/.*browsing/i,
    /zhihu\.com\/api\/v4\/.*recent/i,
    /zhihu\.com\/api\/v4\/.*record_viewed/i,
    /zhihu\.com\/api\/v4\/.*viewed/i,
    /api\.github\.com\/graphql/i,
    /mp\.weixin\.qq\.com\/s\?/i,
    /github\.com\/.*\/starred/i,
  ];

  const REPLY_ACTION = /bilibili\.com\/x\/v2\/reply\/action/i;
  const REPLY_ADD = /bilibili\.com\/x\/v2\/reply\/add/i;

  function shouldCapture(url) {
    return CAPTURE.some((re) => re.test(url));
  }

  function emit(type, url, body) {
    window.postMessage({ source: "osint-capture", type, url, body }, "*");
  }

  function emitCaptureError(url, body) {
    if (!body || typeof body !== "object") return;
    const code = body.code;
    if (code === 0 || code === undefined || code === null) return;
    window.postMessage(
      {
        source: "osint-capture",
        type: "capture_error",
        url,
        body: { code, message: body.message || body.msg || String(code) },
      },
      "*"
    );
  }

  function parseFormBody(body) {
    if (!body) return {};
    try {
      if (typeof body === "string") {
        return Object.fromEntries(new URLSearchParams(body));
      }
      if (body instanceof URLSearchParams) {
        return Object.fromEntries(body);
      }
    } catch (_) {}
    return {};
  }

  async function readRequestBody(init) {
    if (!init || init.body == null) return {};
    const b = init.body;
    if (typeof b === "string") return parseFormBody(b);
    if (b instanceof URLSearchParams) return Object.fromEntries(b);
    if (typeof b.text === "function") {
      try {
        return parseFormBody(await b.text());
      } catch (_) {}
    }
    return {};
  }

  function wrapReplyPostBody(params, responseBody) {
    return {
      code: 0,
      _osint_reply_post: params,
      _osint_response: responseBody || null,
    };
  }

  function wrapReplyActionBody(params, responseBody) {
    return {
      code: 0,
      _osint_reply_action: params,
      _osint_response: responseBody || null,
    };
  }

  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const req = args[0];
    const url = typeof req === "string" ? req : req && req.url ? req.url : "";
    const isReplyAction = url && REPLY_ACTION.test(url);
    const isReplyAdd = url && REPLY_ADD.test(url);

    if (isReplyAdd) {
      const params = await readRequestBody(args[1] || {});
      const res = await origFetch.apply(this, args);
      try {
        res
          .clone()
          .json()
          .then((body) => emit("fetch", url, wrapReplyPostBody(params, body)))
          .catch(() => emit("fetch", url, wrapReplyPostBody(params, null)));
      } catch (_) {}
      return res;
    }

    if (isReplyAction) {
      const params = await readRequestBody(args[1] || {});
      const res = await origFetch.apply(this, args);
      try {
        res
          .clone()
          .json()
          .then((body) => emit("fetch", url, wrapReplyActionBody(params, body)))
          .catch(() => emit("fetch", url, wrapReplyActionBody(params, null)));
      } catch (_) {}
      return res;
    }

    const res = await origFetch.apply(this, args);
    try {
      if (url && shouldCapture(url)) {
        res
          .clone()
          .json()
          .then((body) => {
            emitCaptureError(url, body);
            emit("fetch", url, body);
          })
          .catch(() => {});
      }
    } catch (_) {}
    return res;
  };

  const XHR = XMLHttpRequest.prototype;
  const open = XHR.open;
  const send = XHR.send;
  XHR.open = function (method, url) {
    this._osintUrl = url;
    this._osintMethod = method;
    return open.apply(this, arguments);
  };
  XHR.send = function (body) {
    const url = String(this._osintUrl || "");
    const method = String(this._osintMethod || "").toUpperCase();
    const isReplyAction = REPLY_ACTION.test(url) && method === "POST";
    const isReplyAdd = REPLY_ADD.test(url) && method === "POST";

    if (isReplyAdd) {
      const params = parseFormBody(body);
      this.addEventListener("load", function () {
        let resp = null;
        try {
          if (this.responseText) resp = JSON.parse(this.responseText);
        } catch (_) {}
        emit("xhr", url, wrapReplyPostBody(params, resp));
      });
    } else if (isReplyAction) {
      const params = parseFormBody(body);
      this.addEventListener("load", function () {
        let resp = null;
        try {
          if (this.responseText) resp = JSON.parse(this.responseText);
        } catch (_) {}
        emit("xhr", url, wrapReplyActionBody(params, resp));
      });
    } else {
      this.addEventListener("load", function () {
        try {
          if (!shouldCapture(url) || !this.responseText) return;
          const parsed = JSON.parse(this.responseText);
          emitCaptureError(url, parsed);
          emit("xhr", url, parsed);
        } catch (_) {}
      });
    }
    return send.apply(this, arguments);
  };
})();
