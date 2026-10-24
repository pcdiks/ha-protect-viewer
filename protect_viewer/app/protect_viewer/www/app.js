// Protect Viewer UI. All URLs are relative so the page works under the Ingress path.

const view = document.getElementById('view');
const title = document.getElementById('title');
const back = document.getElementById('back');
const banner = document.getElementById('banner');

const STATUS_INTERVAL = 30000;
let cameras = [];

function wsUrl(stream) {
  return new URL(`api/ws?src=${encodeURIComponent(stream)}`, document.baseURI);
}

function snapshotUrl(camera) {
  return `api/cameras/${encodeURIComponent(camera.id)}/snapshot?t=${Date.now()}`;
}

function player(stream, media) {
  const el = document.createElement('video-stream');
  el.mode = 'webrtc,mse';
  el.media = media;
  el.src = wsUrl(stream);
  return el;
}

// The player creates its <video> once it is attached to the document.
function setupVideos(controls) {
  for (const el of view.querySelectorAll('video-stream')) {
    if (!el.video) continue;
    el.video.controls = controls;
    el.video.poster = el.dataset.poster || '';
  }
}

function notice(text) {
  const el = document.createElement('div');
  el.className = 'notice';
  el.textContent = text;
  return el;
}

function problem(camera) {
  if (!camera.connected) return 'Camera is offline';
  if (!camera.streams) return 'RTSP is not enabled for this camera in Protect';
  return null;
}

function renderGrid() {
  title.textContent = 'Cameras';
  back.hidden = true;
  view.replaceChildren();

  if (!cameras.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'No cameras found.';
    view.append(empty);
    return;
  }

  const grid = document.createElement('div');
  grid.className = 'grid';
  for (const camera of cameras) {
    const tile = document.createElement('div');
    tile.className = 'tile';
    tile.dataset.id = camera.id;
    tile.style.backgroundImage = `url("${snapshotUrl(camera)}")`;
    tile.addEventListener('click', () => { location.hash = `#/camera/${camera.id}`; });

    const issue = problem(camera);
    if (issue) {
      tile.append(notice(issue));
    } else {
      const el = player(camera.streams.grid, 'video');
      el.dataset.poster = snapshotUrl(camera);
      tile.append(el);
    }

    const label = document.createElement('div');
    label.className = 'label';
    const dot = document.createElement('span');
    dot.className = camera.connected ? 'dot' : 'dot off';
    label.append(dot, camera.name);
    tile.append(label);
    grid.append(tile);
  }
  view.append(grid);
  setupVideos(false);
}

function renderCamera(id) {
  const camera = cameras.find(c => c.id === id);
  if (!camera) {
    location.hash = '';
    return;
  }
  title.textContent = camera.name;
  back.hidden = false;
  view.replaceChildren();

  const single = document.createElement('div');
  single.className = 'single';
  const issue = problem(camera);
  if (issue) {
    single.append(notice(issue));
  } else {
    const el = player(camera.streams.main, 'video,audio');
    el.dataset.poster = snapshotUrl(camera);
    single.append(el);
  }
  view.append(single);
  setupVideos(true);
}

function route() {
  const match = location.hash.match(/^#\/camera\/(.+)$/);
  if (match) renderCamera(decodeURIComponent(match[1]));
  else renderGrid();
}

async function load() {
  const resp = await fetch('api/cameras', { cache: 'no-store' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

function showBanner(text) {
  banner.textContent = text || '';
  banner.hidden = !text;
}

// Only re-render when something that changes the players differs, so streams keep running.
function signature(list) {
  return JSON.stringify(list.map(c => [c.id, c.name, c.connected, c.streams]));
}

async function refresh(initial) {
  try {
    const data = await load();
    showBanner(data.error);
    document.body.classList.toggle('hide-stream-type', !data.show_stream_type);
    const changed = signature(data.cameras) !== signature(cameras);
    cameras = data.cameras;
    if (initial || changed) route();
  } catch (err) {
    showBanner(`Cannot reach the add-on: ${err.message}`);
  }
}

back.addEventListener('click', () => {
  if (history.length > 1) history.back();
  else location.hash = '';
});
window.addEventListener('hashchange', route);

refresh(true);
setInterval(() => refresh(false), STATUS_INTERVAL);
