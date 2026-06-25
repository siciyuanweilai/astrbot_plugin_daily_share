import { text } from "./format.js?v=20260614-schedule-modes";
import {
  QZONE_MEDIA_LIMIT,
  QZONE_VIDEO_LIMIT,
  dataUrlToBase64Source,
  postId,
  qzoneMediaFileKind,
  readFileAsDataUrl,
} from "./zonekit.js?v=20260618-qzone-media-video";

export function createQzoneComposer({
  state,
  elements: el,
  apiPost,
  setNotice,
  updateButtons,
  renderQzone,
  reloadStatus,
  loadQzoneFeed,
} = {}) {
  function previewSource(item = {}) {
    const source = text(item.preview || item.source).trim();
    if (!source) return "";
    if (source.startsWith("base64://")) {
      return `data:${text(item.mime_type).trim() || "image/jpeg"};base64,${source.slice("base64://".length)}`;
    }
    return source;
  }

  function captureVideoPreview(file) {
    return new Promise((resolve) => {
      if (!file || typeof URL === "undefined") {
        resolve("");
        return;
      }
      const objectUrl = URL.createObjectURL(file);
      const video = document.createElement("video");
      let settled = false;
      let timer = 0;

      function cleanup() {
        window.clearTimeout(timer);
        video.removeAttribute("src");
        video.load();
        URL.revokeObjectURL(objectUrl);
      }

      function finish(value = "") {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(value);
      }

      function drawFrame() {
        try {
          const width = video.videoWidth || 0;
          const height = video.videoHeight || 0;
          if (!width || !height) {
            finish("");
            return;
          }
          const maxSide = 360;
          const scale = Math.min(1, maxSide / Math.max(width, height));
          const canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round(width * scale));
          canvas.height = Math.max(1, Math.round(height * scale));
          const ctx = canvas.getContext("2d");
          if (!ctx) {
            finish("");
            return;
          }
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          finish(canvas.toDataURL("image/jpeg", 0.82));
        } catch (_error) {
          finish("");
        }
      }

      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.addEventListener("error", () => finish(""), { once: true });
      video.addEventListener("seeked", drawFrame, { once: true });
      video.addEventListener("loadedmetadata", () => {
        const duration = Number(video.duration || 0);
        const target = Number.isFinite(duration) && duration > 0
          ? Math.min(0.6, Math.max(0.08, duration * 0.1))
          : 0;
        if (target > 0) {
          try {
            video.currentTime = target;
          } catch (_error) {
            drawFrame();
          }
          return;
        }
        if (video.readyState >= 2) {
          drawFrame();
        } else {
          video.addEventListener("loadeddata", drawFrame, { once: true });
        }
      }, { once: true });
      timer = window.setTimeout(() => finish(""), 5000);
      video.src = objectUrl;
      video.load();
    });
  }

  function renderComposerMedia() {
    if (!el.qzoneMediaStrip) return;
    const nodes = state.qzoneMedia.map((item, index) => {
      const kind = text(item.kind).trim() === "video" ? "video" : "image";
      const chip = document.createElement("div");
      chip.className = `qzone-media-chip is-${kind}`;
      const src = text(item.preview).trim() || (kind === "image" ? previewSource(item) : "");
      const thumb = document.createElement("span");
      thumb.className = `qzone-media-thumb${kind === "video" && src ? " has-preview" : ""}`;
      if (src) {
        const img = document.createElement("img");
        img.alt = "";
        img.src = src;
        thumb.append(img);
      } else if (kind === "video") {
        thumb.textContent = "视频";
      } else {
        thumb.textContent = "🌸";
      }
      const name = document.createElement("span");
      name.className = "qzone-media-name";
      name.textContent = text(item.name).trim() || `${kind === "video" ? "视频" : "图片"} ${index + 1}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "qzone-media-remove";
      remove.dataset.qzoneMediaIndex = String(index);
      remove.setAttribute("aria-label", `移除第 ${index + 1} 个媒体`);
      remove.textContent = "×";
      chip.append(thumb, name, remove);
      return chip;
    });
    el.qzoneMediaStrip.replaceChildren(...nodes);
    el.qzoneMediaStrip.hidden = !nodes.length;
  }

  async function uploadQzoneFiles(files) {
    const uploads = [...files]
      .map((file) => ({ file, kind: qzoneMediaFileKind(file) }))
      .filter((item) => item.kind);
    if (!uploads.length) return;
    const selectedKinds = new Set(uploads.map((item) => item.kind));
    const existingKinds = new Set(state.qzoneMedia.map((item) => text(item.kind).trim() || "image"));
    if ((selectedKinds.has("video") && (selectedKinds.size > 1 || existingKinds.size > 0)) ||
        (selectedKinds.has("image") && existingKinds.has("video"))) {
      setNotice("QQ 空间视频不能和图片混发，请只保留一种媒体。", "error");
      return;
    }
    if (selectedKinds.has("video") && uploads.length > QZONE_VIDEO_LIMIT) {
      setNotice(`一次只能添加 ${QZONE_VIDEO_LIMIT} 个视频`, "error");
      return;
    }
    state.qzoneMediaReading = true;
    updateButtons();
    try {
      for (const { file, kind } of uploads) {
        if (kind === "image" && state.qzoneMedia.length >= QZONE_MEDIA_LIMIT) {
          setNotice(`最多只能添加 ${QZONE_MEDIA_LIMIT} 张图片`);
          break;
        }
        if (kind === "video" && state.qzoneMedia.length >= QZONE_VIDEO_LIMIT) {
          setNotice(`一次只能添加 ${QZONE_VIDEO_LIMIT} 个视频`, "error");
          break;
        }
        try {
          const [mediaData, videoPreview] = kind === "video"
            ? await Promise.all([readFileAsDataUrl(file), captureVideoPreview(file)])
            : [await readFileAsDataUrl(file), ""];
          const source = dataUrlToBase64Source(mediaData);
          if (!source) throw new Error("媒体读取失败");
          state.qzoneMedia.push({
            kind,
            name: file.name || `${kind === "video" ? "视频" : "图片"} ${state.qzoneMedia.length + 1}`,
            source,
            preview: kind === "image" ? mediaData : videoPreview,
            size: file.size || 0,
            mime_type: file.type || (kind === "video" ? "video/mp4" : "image/jpeg"),
          });
          renderComposerMedia();
        } catch (error) {
          setNotice(error.message || "媒体读取失败", "error");
        }
      }
    } finally {
      state.qzoneMediaReading = false;
      updateButtons();
    }
  }

  async function publishQzone(event) {
    event.preventDefault();
    const content = text(el.qzonePublishText?.value).trim();
    const media = state.qzoneMedia
      .map((item) => {
        const kind = text(item.kind).trim() === "video" ? "video" : "image";
        return {
          kind,
          name: text(item.name).trim(),
          source: text(item.source).trim(),
          mime_type: text(item.mime_type).trim(),
          size: Number(item.size || 0),
          cover: kind === "video" ? text(item.preview).trim() : "",
        };
      })
      .filter((item) => item.source);
    if (!content && !media.length) {
      setNotice("说说内容或媒体不能为空", "error");
      return;
    }
    const hasVideo = media.some((item) => item.kind === "video");
    const processingMessage = media.length
      ? "正在处理媒体并发布 QQ 空间说说，请稍候..."
      : "正在发布 QQ 空间说说，请稍候...";
    state.qzonePublishing = true;
    updateButtons();
    try {
      setNotice(processingMessage, "info");
      const data = await apiPost("page/qzone/publish", { text: content, media }, hasVideo ? 180000 : 65000);
      const item = data.item || data.post;
      if (item) state.qzoneItems = [item, ...state.qzoneItems.filter((old) => postId(old) !== postId(item))].slice(0, 10);
      if (el.qzonePublishText) el.qzonePublishText.value = "";
      state.qzoneMedia = [];
      setNotice("说说已发布", "success");
      renderQzone();
      await reloadStatus?.({ quiet: true });
      await loadQzoneFeed({ quiet: true });
    } catch (error) {
      setNotice(error.message || "说说发布失败", "error");
    } finally {
      state.qzonePublishing = false;
      updateButtons();
    }
  }

  return {
    publishQzone,
    renderComposerMedia,
    uploadQzoneFiles,
  };
}
