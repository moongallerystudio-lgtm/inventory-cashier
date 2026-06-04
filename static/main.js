// Cleaned main.js: scanning (BarcodeDetector + Quagga fallback), cart, member, receipt
let currentScanTarget = null;
let videoStream = null;
let barcodeDetector = null;
let quaggaRunning = false;
let currentMember = null;
let lastImageDataUrl = null;
let lastRotation = 0;
let audioContext = null;

function getAudioContext() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  if (!audioContext) audioContext = new AudioContextClass();
  if (audioContext.state === 'suspended') {
    audioContext.resume().catch(() => {});
  }
  return audioContext;
}

function playToneSequence(notes) {
  const ctx = getAudioContext();
  if (!ctx) return;
  const start = ctx.currentTime + 0.01;
  notes.forEach((note) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(note.freq, start + note.at);
    gain.gain.setValueAtTime(0.0001, start + note.at);
    gain.gain.exponentialRampToValueAtTime(note.volume || 0.16, start + note.at + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + note.at + note.duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(start + note.at);
    osc.stop(start + note.at + note.duration + 0.03);
  });
}

function playScanSound() {
  playToneSequence([
    { freq: 1046.5, at: 0, duration: 0.09, volume: 0.13 },
    { freq: 1568, at: 0.08, duration: 0.12, volume: 0.15 },
  ]);
}

function playCheckoutSound() {
  playToneSequence([
    { freq: 783.99, at: 0, duration: 0.12, volume: 0.13 },
    { freq: 1046.5, at: 0.12, duration: 0.14, volume: 0.15 },
    { freq: 1318.51, at: 0.26, duration: 0.2, volume: 0.16 },
  ]);
}

function tr(key, fallback, params = {}) {
  const dict = window.APP_I18N || {};
  let text = dict[key] || fallback;
  for (const [name, value] of Object.entries(params)) {
    text = text.replace(`{${name}}`, value);
  }
  return text;
}

function formatJpy(value) {
  return String(Math.round(Number(value) || 0));
}

function formatJpyWithSymbol(value) {
  return `¥${formatJpy(value)}`;
}

async function startScan(targetId) {
  currentScanTarget = targetId;
  const videoWrapper = document.getElementById('videoWrapper');
  const scanVideo = document.getElementById('scanVideo');

  console.log('startScan target:', targetId);
  const isLocalhost = ['localhost', '127.0.0.1', '::1'].includes(location.hostname);
  if (!window.isSecureContext && !isLocalhost) {
    alert('当前访问不是安全上下文，浏览器无法直接打开摄像头。请通过 HTTPS 地址访问或手动输入条码。');
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('当前浏览器不支持摄像头访问，无法进行实时扫码。请手动输入条码。');
    return;
  }

  // Prefer native BarcodeDetector when available
  if ('BarcodeDetector' in window) {
    try {
      barcodeDetector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'code_128', 'qr_code', 'upc_e'] });
    } catch (error) {
      barcodeDetector = null;
    }
  }

  if (barcodeDetector) {
    try {
      videoStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      scanVideo.srcObject = videoStream;
      scanVideo.muted = true;
      videoWrapper.style.display = 'block';
      await scanVideo.play();
      scanFrame();
      return;
    } catch (error) {
      console.warn('摄像头打开或视频播放失败', error);
      alert('无法打开摄像头或自动播放视频失败：' + error.message + '。请手动输入条码或检查浏览器权限。');
      return;
    }
  }

  // Fallback: use QuaggaJS (loaded from CDN in templates)
  if (window.Quagga) {
    startQuagga(videoWrapper);
  } else {
    // Try to dynamically load Quagga, then start
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@ericblade/quagga2/dist/quagga.min.js';
    script.onload = () => startQuagga(videoWrapper);
    script.onerror = () => alert('无法加载扫码回退库，请手动输入条形码。');
    document.head.appendChild(script);
  }
}

function startQuagga(videoWrapper) {
  if (!window.Quagga) {
    alert('扫码回退库未加载，请手动输入条形码。');
    return;
  }
  if (quaggaRunning) return;
  quaggaRunning = true;
  videoWrapper.style.display = 'block';
  Quagga.init({
    inputStream: {
      name: 'Live',
      type: 'LiveStream',
      target: videoWrapper,
      constraints: { facingMode: 'environment' },
    },
    decoder: {
      readers: ['ean_reader','ean_8_reader','code_128_reader','code_39_reader','upc_reader']
    },
    locate: true,
  }, function(err) {
    if (err) {
      console.error(err);
      alert('初始化扫码失败，请手动输入条形码。');
      quaggaRunning = false;
      videoWrapper.style.display = 'none';
      return;
    }
    Quagga.start();
  });
  Quagga.onDetected(function(result) {
    if (!result || !result.codeResult) return;
    const code = result.codeResult.code;
    stopQuagga();
    fillBarcode(code);
  });
}

function stopQuagga() {
  if (!quaggaRunning) return;
  try {
    Quagga.stop();
  } catch (e) {
    console.warn('Quagga stop error', e);
  }
  quaggaRunning = false;
  const videoWrapper = document.getElementById('videoWrapper');
  if (videoWrapper) videoWrapper.style.display = 'none';
}

async function scanFrame() {
  if (!videoStream) return;
  const scanVideo = document.getElementById('scanVideo');

  if (barcodeDetector) {
    try {
      const barcodes = await barcodeDetector.detect(scanVideo);
      if (barcodes && barcodes.length > 0) {
        const code = barcodes[0].rawValue;
        stopScan();
        fillBarcode(code);
        return;
      }
    } catch (error) {
      console.warn('BarcodeDetector error', error);
    }
  }

  requestAnimationFrame(scanFrame);
}

function stopScan() {
  stopQuagga();
  const videoWrapper = document.getElementById('videoWrapper');
  const scanVideo = document.getElementById('scanVideo');

  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
    videoStream = null;
  }
  if (scanVideo) scanVideo.srcObject = null;
  if (videoWrapper) videoWrapper.style.display = 'none';
}

function fillBarcode(code) {
  const input = document.getElementById(currentScanTarget);
  if (input) {
    input.value = code;
    input.focus();
  }
}

function openImageInput() {
  let fileInput = document.getElementById('scanImageInput');
  if (!fileInput) {
    fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.capture = 'environment';
    fileInput.id = 'scanImageInput';
    fileInput.style.position = 'absolute';
    fileInput.style.left = '-9999px';
    fileInput.style.opacity = '0';
    fileInput.style.width = '1px';
    fileInput.style.height = '1px';
    fileInput.addEventListener('change', handleImageFile);
    document.body.appendChild(fileInput);
  }
  try {
    fileInput.value = '';
  } catch (e) {
    // some browsers disallow programmatic clearing, ignore
  }
  fileInput.click();
}

function handleImageFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }
  decodeImageFile(file);
}

function decodeImageFile(file) {
  if (!window.Quagga) {
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@ericblade/quagga2/dist/quagga.min.js';
    script.onload = () => decodeImageFile(file);
    script.onerror = () => alert('无法加载扫码回退库，请手动输入条形码。');
    document.head.appendChild(script);
    return;
  }

  const resultEl = document.getElementById('scanResult');
  if (resultEl) resultEl.textContent = '正在识别图片，请稍候……';

  const img = new Image();
  const objectUrl = URL.createObjectURL(file);
  img.onload = async () => {
    try {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      // try different scales and rotations
      const attempts = [];
      const maxDim = 1200; // limit large images
      let w = img.naturalWidth;
      let h = img.naturalHeight;
      const scale = Math.min(1, maxDim / Math.max(w, h));
      w = Math.round(w * scale);
      h = Math.round(h * scale);

      // attempt auto-crop from the scaled full image first
      const baseCanvas = document.createElement('canvas');
      baseCanvas.width = w; baseCanvas.height = h;
      const baseCtx = baseCanvas.getContext('2d');
      baseCtx.drawImage(img, 0, 0, w, h);
      const crops = await autoCropImageFromCanvas(baseCanvas);

      const rotations = [0, 90, 270, 180];
      // if auto-crop produced crops, prepend them to attempts to try first
      if (crops && crops.length > 0) {
        for (const c of crops) attempts.push(c);
      }
      for (const rot of rotations) {
        // prepare canvas for rotation
        if (rot === 90 || rot === 270) {
          canvas.width = h;
          canvas.height = w;
        } else {
          canvas.width = w;
          canvas.height = h;
        }
        // draw with rotation
        ctx.save();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (rot !== 0) {
          ctx.translate(canvas.width / 2, canvas.height / 2);
          ctx.rotate(rot * Math.PI / 180);
          ctx.drawImage(img, -w / 2, -h / 2, w, h);
        } else {
          ctx.drawImage(img, 0, 0, w, h);
        }
        ctx.restore();

        // simple contrast/brightness adjustment to help decoder
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const data = imageData.data;
        // convert to grayscale and enhance contrast
        for (let i = 0; i < data.length; i += 4) {
          const r = data[i], g = data[i+1], b = data[i+2];
          const gray = (r * 0.299 + g * 0.587 + b * 0.114);
          // increase contrast around mid-tone
          const contrasted = Math.max(0, Math.min(255, (gray - 128) * 1.4 + 128));
          data[i] = data[i+1] = data[i+2] = contrasted;
        }
        ctx.putImageData(imageData, 0, 0);

        const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
        attempts.push(dataUrl);
      }

      // try decode attempts sequentially
      for (const src of attempts) {
        // eslint-disable-next-line no-await-in-loop
        const res = await new Promise(resolve => {
          Quagga.decodeSingle({
            src,
            numOfWorkers: 0,
            decoder: { readers: ['ean_reader','ean_8_reader','code_128_reader','code_39_reader','upc_reader'] },
            locate: true
          }, resolve);
        });
        if (res && res.codeResult && res.codeResult.code) {
          fillBarcode(res.codeResult.code);
          if (resultEl) resultEl.textContent = `识别成功：${res.codeResult.code}`;
          URL.revokeObjectURL(objectUrl);
          // clear preview state
          lastImageDataUrl = null;
          lastRotation = 0;
          closePreview();
          return;
        }
      }

      // if none succeeded, keep a preview and allow user to rotate/retry
      URL.revokeObjectURL(objectUrl);
      if (attempts && attempts.length > 0) {
        lastImageDataUrl = attempts[0];
        lastRotation = 0;
        setPreview(lastImageDataUrl);
        if (resultEl) resultEl.textContent = '识别失败，可旋转图片后重试。';
      } else {
        if (resultEl) resultEl.textContent = '';
        alert('图片识别失败，请确保条码完整、清晰、并尽量垂直拍摄后重试。');
      }
    } catch (err) {
      URL.revokeObjectURL(objectUrl);
      console.error('decodeImageFile error', err);
      if (resultEl) resultEl.textContent = '';
      alert('图片识别出错，请重试或手动输入条形码。');
    }
  };
  img.onerror = () => {
    URL.revokeObjectURL(objectUrl);
    alert('无法读取图片文件，请重试。');
  };
  img.src = objectUrl;
}

function setPreview(dataUrl) {
  const container = document.getElementById('scanPreviewContainer');
  const img = document.getElementById('scanPreview');
  if (img && container) {
    img.src = dataUrl;
    container.style.display = 'block';
  }
}

// Try to auto-crop likely barcode region from a canvas and return data URLs
async function autoCropImageFromCanvas(canvas) {
  try {
    const w = canvas.width, h = canvas.height;
    const ctx = canvas.getContext('2d');
    const imgData = ctx.getImageData(0, 0, w, h);
    const data = imgData.data;

    // Compute vertical edge strength per column (sum of abs horizontal differences)
    const colScores = new Float32Array(w);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w - 1; x++) {
        const i = (y * w + x) * 4;
        const r = data[i], g = data[i+1], b = data[i+2];
        const r2 = data[i+4], g2 = data[i+5], b2 = data[i+6];
        const gray = 0.299*r + 0.587*g + 0.114*b;
        const gray2 = 0.299*r2 + 0.587*g2 + 0.114*b2;
        colScores[x] += Math.abs(gray2 - gray);
      }
    }

    // Smooth scores with simple box filter
    const smooth = new Float32Array(w);
    const radius = Math.max(1, Math.round(w * 0.01));
    for (let x = 0; x < w; x++) {
      let sum = 0, cnt = 0;
      for (let k = -radius; k <= radius; k++) {
        const xi = x + k;
        if (xi >= 0 && xi < w) { sum += colScores[xi]; cnt++; }
      }
      smooth[x] = sum / Math.max(1, cnt);
    }

    // Find segments where score > threshold
    let mean = 0; for (let i=0;i<w;i++) mean += smooth[i]; mean /= w;
    let variance = 0; for (let i=0;i<w;i++) { const d = smooth[i]-mean; variance += d*d; } variance /= w;
    const std = Math.sqrt(variance);
    const thresh = mean + std * 0.5;

    let segments = [];
    let inSeg = false, segStart = 0;
    for (let x = 0; x < w; x++) {
      if (smooth[x] >= thresh) {
        if (!inSeg) { inSeg = true; segStart = x; }
      } else {
        if (inSeg) { inSeg = false; segments.push([segStart, x-1]); }
      }
    }
    if (inSeg) segments.push([segStart, w-1]);

    if (segments.length === 0) return [];

    // Choose largest segment width
    segments.sort((a,b) => (b[1]-b[0]) - (a[1]-a[0]));
    const [sx, ex] = segments[0];

    // For rows, compute sum of column differences within selected columns to find vertical bounds
    const colL = Math.max(0, sx - Math.round((ex-sx)*0.2));
    const colR = Math.min(w-1, ex + Math.round((ex-sx)*0.2));
    const rowScores = new Float32Array(h);
    for (let y = 0; y < h - 1; y++) {
      let sum = 0;
      for (let x = colL; x <= colR; x++) {
        const i = (y * w + x) * 4;
        const r = data[i], g = data[i+1], b = data[i+2];
        const i2 = ((y+1) * w + x) * 4;
        const r2 = data[i2], g2 = data[i2+1], b2 = data[i2+2];
        const gray = 0.299*r + 0.587*g + 0.114*b;
        const gray2 = 0.299*r2 + 0.587*g2 + 0.114*b2;
        sum += Math.abs(gray2 - gray);
      }
      rowScores[y] = sum;
    }

    // Smooth rows
    const rsmooth = new Float32Array(h);
    const rr = Math.max(1, Math.round(h * 0.01));
    for (let y = 0; y < h; y++) {
      let sum = 0, cnt = 0;
      for (let k = -rr; k <= rr; k++) {
        const yi = y + k;
        if (yi >= 0 && yi < h) { sum += rowScores[yi]; cnt++; }
      }
      rsmooth[y] = sum / Math.max(1, cnt);
    }

    let rmean = 0; for (let i=0;i<h;i++) rmean += rsmooth[i]; rmean /= h;
    let rvar = 0; for (let i=0;i<h;i++){ const d = rsmooth[i]-rmean; rvar += d*d; } rvar/=h;
    const rstd = Math.sqrt(rvar);
    const rthresh = rmean + rstd * 0.3;

    let rsegments = [], rin=false, rstart=0;
    for (let y=0;y<h;y++){
      if (rsmooth[y] >= rthresh) { if(!rin){ rin=true; rstart=y; } }
      else { if(rin){ rin=false; rsegments.push([rstart,y-1]); } }
    }
    if (rin) rsegments.push([rstart,h-1]);
    if (rsegments.length === 0) return [];

    rsegments.sort((a,b)=>(b[1]-b[0])-(a[1]-a[0]));
    const [sy, ey] = rsegments[0];

    // add padding
    const padX = Math.round((ex - sx) * 0.2) + 10;
    const padY = Math.round((ey - sy) * 0.2) + 10;
    const cx1 = Math.max(0, sx - padX);
    const cx2 = Math.min(w-1, ex + padX);
    const cy1 = Math.max(0, sy - padY);
    const cy2 = Math.min(h-1, ey + padY);

    const cropW = cx2 - cx1 + 1;
    const cropH = cy2 - cy1 + 1;
    if (cropW < 30 || cropH < 30) return [];

    const cropCanvas = document.createElement('canvas');
    cropCanvas.width = cropW;
    cropCanvas.height = cropH;
    const cctx = cropCanvas.getContext('2d');
    cctx.drawImage(canvas, cx1, cy1, cropW, cropH, 0, 0, cropW, cropH);
    const dataUrl = cropCanvas.toDataURL('image/jpeg', 0.95);
    return [dataUrl];
  } catch (e) {
    console.warn('autoCropImageFromCanvas failed', e);
    return [];
  }
}

function closePreview() {
  const container = document.getElementById('scanPreviewContainer');
  const img = document.getElementById('scanPreview');
  const resultEl = document.getElementById('scanResult');
  if (img) img.src = '';
  if (container) container.style.display = 'none';
  if (resultEl) resultEl.textContent = '';
  lastImageDataUrl = null;
  lastRotation = 0;
}

async function decodeFromDataUrl(dataUrl) {
  return new Promise(resolve => {
    Quagga.decodeSingle({
      src: dataUrl,
      numOfWorkers: 0,
      decoder: { readers: ['ean_reader','ean_8_reader','code_128_reader','code_39_reader','upc_reader'] },
      locate: true
    }, resolve);
  });
}

async function rotatePreview(angle) {
  if (!lastImageDataUrl) return;
  lastRotation = (lastRotation + angle + 360) % 360;
  // draw image to canvas with rotation
  const img = document.createElement('img');
  img.src = lastImageDataUrl;
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; });
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  let w = img.naturalWidth, h = img.naturalHeight;
  const rot = lastRotation % 360;
  if (rot === 90 || rot === 270) {
    canvas.width = h; canvas.height = w;
    ctx.translate(canvas.width/2, canvas.height/2);
    ctx.rotate(rot * Math.PI/180);
    ctx.drawImage(img, -w/2, -h/2, w, h);
  } else {
    canvas.width = w; canvas.height = h;
    ctx.translate(canvas.width/2, canvas.height/2);
    ctx.rotate(rot * Math.PI/180);
    ctx.drawImage(img, -w/2, -h/2, w, h);
  }
  const newDataUrl = canvas.toDataURL('image/jpeg', 0.9);
  lastImageDataUrl = newDataUrl;
  setPreview(newDataUrl);
}

async function retryPreview() {
  if (!lastImageDataUrl) return;
  const resultEl = document.getElementById('scanResult');
  if (resultEl) resultEl.textContent = '重新识别中……';
  const res = await decodeFromDataUrl(lastImageDataUrl);
  if (res && res.codeResult && res.codeResult.code) {
    fillBarcode(res.codeResult.code);
    if (resultEl) resultEl.textContent = `识别成功：${res.codeResult.code}`;
    closePreview();
  } else {
    if (resultEl) resultEl.textContent = '识别失败，请尝试旋转图片或更换拍摄角度。';
  }
}

async function scanCashierBarcode() {
  const barcodeInput = document.getElementById('cashierBarcode');
  const resultEl = document.getElementById('scanResult');
  const barcode = barcodeInput.value.trim();
  resultEl.textContent = '';
  if (!barcode) {
    resultEl.textContent = '请输入条形码后再添加。';
    return;
  }

  const response = await fetch('/api/cashier/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ barcode }),
  });

  const data = await response.json();
  if (!response.ok) {
    resultEl.textContent = data.error || '添加商品失败';
    return;
  }

  resultEl.textContent = `已加入：${data.product.name} ${formatJpyWithSymbol(data.product.price)}，数量 ${data.product.qty}`;
  updateCartTable(data.cart.items, data.cart.total);
  playScanSound();
  barcodeInput.value = '';
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeJsString(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function updateCartTable(items, total) {
  const body = document.getElementById('cartBody');
  const totalEl = document.getElementById('cartTotal');
  const payableEl = document.getElementById('cartPayable');
  body.innerHTML = '';

  if (!items || items.length === 0) {
    body.innerHTML = `<tr><td colspan="5">${escapeHtml(tr('emptyCart', '购物车为空'))}</td></tr>`;
  } else {
    for (const item of items) {
      const rawBarcode = String(item.barcode);
      const barcode = escapeHtml(rawBarcode);
      const name = escapeHtml(item.name);
      const barcodeArg = escapeJsString(rawBarcode);
      const row = document.createElement('tr');
      row.dataset.name = item.name;
      row.dataset.price = item.price;
      row.dataset.qty = item.qty;
      row.dataset.subtotal = item.subtotal;
      row.innerHTML = `
        <td>
          <strong>${name}</strong><br>
          <span class="product-meta">${barcode}</span>
        </td>
        <td>${formatJpyWithSymbol(item.price)}</td>
        <td class="qty-cell">
          <button class="button small" type="button" onclick="changeCartQty('${barcodeArg}', ${item.qty - 1})">-</button>
          <span class="qty-value">${item.qty}</span>
          <button class="button small" type="button" onclick="changeCartQty('${barcodeArg}', ${item.qty + 1})">+</button>
        </td>
        <td>${formatJpyWithSymbol(item.subtotal)}</td>
        <td><button class="button small red" type="button" onclick="removeCartItem('${barcodeArg}')">${escapeHtml(tr('remove', '移除'))}</button></td>
      `;
      body.appendChild(row);
    }
  }
  if (totalEl) totalEl.textContent = formatJpy(total);
  if (payableEl) payableEl.textContent = formatJpy(applyDiscount(total));
}

async function changeCartQty(barcode, qty) {
  if (qty <= 0 && !confirm(tr('removeItemConfirm', '确认从购物车移除这个商品？'))) return;
  const resultEl = document.getElementById('scanResult');
  const response = await fetch(`/api/cashier/cart/${encodeURIComponent(barcode)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ qty }),
  });
  const data = await response.json();
  if (!response.ok) {
    if (resultEl) resultEl.textContent = data.error || '更新购物车失败';
    if (data.cart) updateCartTable(data.cart.items, data.cart.total);
    return;
  }
  if (resultEl) resultEl.textContent = qty <= 0 ? tr('itemRemoved', '已移除商品。') : tr('cartUpdated', '购物车已更新。');
  updateCartTable(data.cart.items, data.cart.total);
  if (qty > 0) playScanSound();
}

function renderProductResults(products) {
  const container = document.getElementById('productResults');
  const status = document.getElementById('productSearchStatus');
  if (!container) return;
  container.innerHTML = '';

  const backButton = document.createElement('button');
  backButton.type = 'button';
  backButton.className = 'button gray artist-back';
  backButton.textContent = tr('backToArtists', '返回艺术家列表');
  backButton.onclick = () => searchProducts();
  container.appendChild(backButton);

  if (!products || products.length === 0) {
    if (status) status.textContent = tr('noProductsFound', '没有找到匹配商品。');
    return;
  }

  for (const product of products) {
    const button = document.createElement('button');
    const disabled = product.stock <= 0;
    button.type = 'button';
    button.className = 'product-tile';
    button.disabled = disabled;
    button.onclick = () => addProductByBarcode(product.barcode);

    const image = product.image_url
      ? `<img class="product-thumb" src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" onerror="this.onerror=null;this.src='/static/logo.jpg';">`
      : `<div class="product-thumb product-placeholder">${escapeHtml(tr('noImage', '无图'))}</div>`;
    const artistLine = product.artist
      ? `${escapeHtml(tr('artist', '艺术家'))}: ${escapeHtml(product.artist)}<br>`
      : '';

    button.innerHTML = `
      ${image}
      <span>
        <span class="product-name">${escapeHtml(product.name)}</span>
        <span class="product-meta">${artistLine}${formatJpyWithSymbol(product.price)} ｜ ${escapeHtml(tr('stock', '库存'))} ${product.stock}<br>${escapeHtml(product.barcode)}</span>
      </span>
    `;
    container.appendChild(button);
  }

  if (status) status.textContent = tr('foundProducts', '找到 {count} 个商品。', { count: products.length });
}

function renderArtistResults(artists) {
  const container = document.getElementById('productResults');
  const status = document.getElementById('productSearchStatus');
  if (!container) return;
  container.innerHTML = '';

  if (!artists || artists.length === 0) {
    if (status) status.textContent = tr('noArtistsFound', '没有找到匹配艺术家。');
    return;
  }

  for (const artist of artists) {
    const artistName = artist.name || '';
    const artistLabel = artistName || tr('noArtistName', '未设置艺术家');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'artist-tile';
    button.onclick = () => showArtistProducts(artistName);
    button.innerHTML = `
      <span class="product-name">${escapeHtml(artistLabel)}</span>
      <span class="product-meta">${escapeHtml(tr('artistProductCount', '{count} 件商品', { count: artist.count }))}</span>
    `;
    container.appendChild(button);
  }

  if (status) status.textContent = tr('foundArtists', '找到 {count} 位艺术家。', { count: artists.length });
}

function filterInventoryTable() {
  const input = document.getElementById('inventorySearch');
  const rows = Array.from(document.querySelectorAll('.inventory-row'));
  const noMatchRow = document.getElementById('inventoryNoMatchRow');
  const keyword = input ? input.value.trim().toLowerCase() : '';
  let visibleCount = 0;

  for (const row of rows) {
    const haystack = row.dataset.search || row.textContent.toLowerCase();
    const visible = !keyword || haystack.includes(keyword);
    row.style.display = visible ? '' : 'none';
    if (visible) visibleCount += 1;
  }

  if (noMatchRow) {
    noMatchRow.style.display = rows.length > 0 && visibleCount === 0 ? '' : 'none';
  }
}

function resetInventoryProductForm() {
  const form = document.getElementById('productForm');
  const barcodeInput = document.getElementById('barcode');
  if (form) form.reset();
  if (barcodeInput) {
    barcodeInput.readOnly = false;
    barcodeInput.focus();
  }
}

function editInventoryProduct(barcode, name, price, stock) {
  const barcodeInput = document.getElementById('barcode');
  const nameInput = document.getElementById('productName');
  const priceInput = document.getElementById('productPrice');
  const stockInput = document.getElementById('productStock');
  const imageInput = document.getElementById('productImage');
  const formPanel = document.getElementById('productFormPanel');

  if (barcodeInput) {
    barcodeInput.value = barcode;
    barcodeInput.readOnly = true;
  }
  if (nameInput) nameInput.value = name;
  if (priceInput) priceInput.value = formatJpy(price);
  if (stockInput) stockInput.value = stock;
  if (imageInput) imageInput.value = '';
  if (formPanel) formPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  if (nameInput) nameInput.focus();
}

async function searchProducts() {
  const input = document.getElementById('productSearch');
  const status = document.getElementById('productSearchStatus');
  const keyword = input ? input.value.trim() : '';
  if (status) status.textContent = tr('searching', '正在搜索...');

  const response = await fetch(`/api/artists?q=${encodeURIComponent(keyword)}`);
  const data = await response.json();
  if (!response.ok) {
    if (status) status.textContent = data.error || '搜索失败';
    return;
  }
  renderArtistResults(data.artists);
}

async function showArtistProducts(artist) {
  const status = document.getElementById('productSearchStatus');
  if (status) status.textContent = tr('searching', '正在搜索...');

  const response = await fetch(`/api/products/search?artist=${encodeURIComponent(artist)}`);
  const data = await response.json();
  if (!response.ok) {
    if (status) status.textContent = data.error || '搜索失败';
    return;
  }
  renderProductResults(data.products);
}

async function addProductByBarcode(barcode) {
  const barcodeInput = document.getElementById('cashierBarcode');
  if (barcodeInput) barcodeInput.value = barcode;
  await scanCashierBarcode();
  await searchProducts();
}

async function removeCartItem(barcode) {
  if (!confirm(tr('removeItemConfirm', '确认从购物车移除这个商品？'))) return;
  const resultEl = document.getElementById('scanResult');
  const response = await fetch(`/api/cashier/cart/${encodeURIComponent(barcode)}`, {
    method: 'DELETE',
  });
  const data = await response.json();
  if (!response.ok) {
    if (resultEl) resultEl.textContent = data.error || '移除商品失败';
    return;
  }
  if (resultEl) resultEl.textContent = tr('itemRemoved', '已移除商品。');
  updateCartTable(data.cart.items, data.cart.total);
}

async function verifyMember() {
  const memberId = document.getElementById('memberId').value.trim();
  const memberInfo = document.getElementById('memberInfo');

  if (!memberId) {
    memberInfo.textContent = '请输入会员卡号进行验证。';
    return;
  }

  const response = await fetch(`/api/member/${encodeURIComponent(memberId)}`);
  const data = await response.json();
  if (!response.ok) {
    memberInfo.textContent = data.error || '会员验证失败';
    currentMember = null;
    updateTotals();
    return;
  }
  currentMember = data.member;
  memberInfo.textContent = `会员：${currentMember.name}，折扣 ${currentMember.discount}% 已应用。`;
  updateTotals();
}

function clearMember() {
  currentMember = null;
  const mid = document.getElementById('memberId');
  if (mid) mid.value = '';
  const memberInfo = document.getElementById('memberInfo');
  if (memberInfo) memberInfo.textContent = '当前未应用会员折扣。';
  updateTotals();
}

function applyDiscount(total) {
  const m = currentMember;
  if (!m || !m.discount) return total;
  return total * (1 - m.discount / 100);
}

function updateTotals() {
  const totalEl = document.getElementById('cartTotal');
  const payableEl = document.getElementById('cartPayable');
  const currentTotal = parseFloat(totalEl ? totalEl.textContent : '0') || 0;
  if (payableEl) payableEl.textContent = formatJpy(applyDiscount(currentTotal));
}

function buildReceipt(items, total) {
  const discountText = currentMember ? `${currentMember.discount}%` : '无';
  const payable = formatJpy(applyDiscount(total));
  const date = new Date().toLocaleString();
  const lines = items.map(item => `
    <tr>
      <td>${escapeHtml(item.name)}</td>
      <td>${item.qty}</td>
      <td>${formatJpyWithSymbol(item.price)}</td>
      <td>${formatJpyWithSymbol(item.subtotal)}</td>
    </tr>
  `).join('');
  return `
    <html>
      <head>
        <title>小票</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 20px; }
          h2 { margin-top: 0; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; }
          td, th { border: 1px solid #ccc; padding: 8px; text-align: left; }
          .summary { margin-top: 16px; font-size: 1.1em; }
        </style>
      </head>
      <body>
        <h2>收银小票</h2>
        <p>时间：${date}</p>
        <p>会员：${currentMember ? escapeHtml(currentMember.name) : '无'}（折扣 ${escapeHtml(discountText)}）</p>
        <table>
          <thead>
            <tr><th>商品</th><th>数量</th><th>单价</th><th>小计</th></tr>
          </thead>
          <tbody>
            ${lines}
          </tbody>
        </table>
        <div class="summary">
          <p>原总价：${formatJpyWithSymbol(total)}</p>
          <p>折后价：¥${payable}</p>
        </div>
      </body>
    </html>
  `;
}

function printReceipt() {
  const items = [];
  document.querySelectorAll('#cartBody tr').forEach(row => {
    if (row.dataset && row.dataset.name) {
      items.push({
        name: row.dataset.name,
        qty: parseFloat(row.dataset.qty) || 0,
        price: parseFloat(row.dataset.price) || 0,
        subtotal: parseFloat(row.dataset.subtotal) || 0,
      });
    }
  });
  const total = parseFloat(document.getElementById('cartTotal').textContent || '0') || 0;
  const receiptWindow = window.open('', 'receipt');
  if (!receiptWindow) {
    alert('请允许弹出窗口以打印小票。');
    return;
  }
  receiptWindow.document.write(buildReceipt(items, total));
  receiptWindow.document.close();
  receiptWindow.focus();
  receiptWindow.print();
}

async function checkout() {
  if (!confirm('确认结账并扣减库存吗？')) return;
  const memberId = document.getElementById('memberId') ? document.getElementById('memberId').value.trim() : '';
  const paymentInput = document.querySelector('input[name="paymentMethod"]:checked');
  const paymentMethod = paymentInput ? paymentInput.value : '现金';
  const response = await fetch('/api/cashier/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ member_id: memberId, payment_method: paymentMethod }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || '结账失败');
    return;
  }
  playCheckoutSound();
  alert(data.message || '结账完成');
  window.location.reload();
}

async function cancelCart() {
  if (!confirm('确认取消本次购物车内容吗？')) return;
  const response = await fetch('/api/cashier/cancel', { method: 'POST' });
  if (response.ok) {
    window.location.reload();
  }
}

// Global error handler to help debugging in mobile browsers
window.addEventListener('error', function(e) {
  try {
    const el = document.getElementById('scanResult');
    if (el) el.textContent = '脚本错误: ' + (e && e.message ? e.message : String(e));
  } catch (ex) {}
});

document.addEventListener('DOMContentLoaded', function() {
  const barcodeInput = document.getElementById('cashierBarcode');
  if (barcodeInput) {
    barcodeInput.focus();
    barcodeInput.addEventListener('keydown', function(event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        scanCashierBarcode();
      }
    });
  }

  const productSearch = document.getElementById('productSearch');
  if (productSearch) {
    let searchTimer = null;
    productSearch.addEventListener('input', function() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(searchProducts, 250);
    });
    productSearch.addEventListener('keydown', function(event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        searchProducts();
      }
    });
    searchProducts();
  }

  const inventorySearch = document.getElementById('inventorySearch');
  if (inventorySearch) {
    inventorySearch.addEventListener('input', filterInventoryTable);
    inventorySearch.addEventListener('keydown', function(event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        filterInventoryTable();
      }
    });
  }

  const clearInventorySearch = document.getElementById('clearInventorySearch');
  if (clearInventorySearch) {
    clearInventorySearch.addEventListener('click', function() {
      if (inventorySearch) {
        inventorySearch.value = '';
        inventorySearch.focus();
      }
      filterInventoryTable();
    });
  }

  const resetProductForm = document.getElementById('resetProductForm');
  if (resetProductForm) {
    resetProductForm.addEventListener('click', resetInventoryProductForm);
  }
});
