const PIECES = {
  P: "wp", N: "wn", B: "wb", R: "wr", Q: "wq", K: "wk",
  p: "bp", n: "bn", b: "bb", r: "br", q: "bq", k: "bk",
};

const boardElement = document.querySelector("#board");
const gameElement = document.querySelector("#game");
const welcomeElement = document.querySelector("#welcome");
const statusElement = document.querySelector("#status");
const retryButton = document.querySelector("#retry");
const promotionDialog = document.querySelector("#promotion");
let game = null;
let selected = null;
let busy = false;
let receivedAt = 0;
let jevError = null;
let runNumber = 0;

function positionFromFen(fen) {
  const position = {};
  const ranks = fen.split(" ")[0].split("/");
  ranks.forEach((rank, rankIndex) => {
    let file = 0;
    for (const token of rank) {
      if (/\d/.test(token)) file += Number(token);
      else {
        position[`${"abcdefgh"[file]}${8 - rankIndex}`] = token;
        file += 1;
      }
    }
  });
  return position;
}

function squares() {
  const whiteOrientation = game.human_color !== "black";
  const files = whiteOrientation ? [..."abcdefgh"] : [..."hgfedcba"];
  const ranks = whiteOrientation ? [8,7,6,5,4,3,2,1] : [1,2,3,4,5,6,7,8];
  return ranks.flatMap(rank => files.map(file => `${file}${rank}`));
}

function legalFrom(square) {
  return game.legal_moves.filter(move => move.slice(0, 2) === square);
}

function renderBoard() {
  const position = positionFromFen(game.fen);
  const last = game.last_move ? [game.last_move.slice(0, 2), game.last_move.slice(2, 4)] : [];
  const targets = selected ? legalFrom(selected).map(move => move.slice(2, 4)) : [];
  const checkedKing = game.in_check
    ? Object.keys(position).find(square => position[square] === (game.turn === "white" ? "K" : "k"))
    : null;
  boardElement.replaceChildren();
  squares().forEach((square, index) => {
    const button = document.createElement("button");
    const piece = position[square];
    button.type = "button";
    button.className = "square";
    button.dataset.square = square;
    button.setAttribute("role", "gridcell");
    button.setAttribute("aria-label", `${square}${piece ? ` ${piece}` : ""}`);
    if (("abcdefgh".indexOf(square[0]) + Number(square[1])) % 2 === 1) button.classList.add("dark");
    if (last.includes(square)) button.classList.add("last");
    if (square === selected) button.classList.add("selected");
    if (targets.includes(square)) button.classList.add("target");
    if (piece) button.classList.add("occupied");
    if (square === checkedKing) button.classList.add("check");
    if (canInteract() && (legalFrom(square).length || targets.includes(square))) button.classList.add("selectable");
    if (piece) button.innerHTML = `<img class="piece" src="/pieces/${PIECES[piece]}.svg" alt="">`;
    if (index % 8 === 0) button.insertAdjacentHTML("beforeend", `<span class="coordinate">${square[1]}</span>`);
    button.draggable = Boolean(piece && canInteract() && legalFrom(square).length);
    button.addEventListener("click", () => clickSquare(square));
    button.addEventListener("dragstart", event => startDrag(event, square));
    button.addEventListener("dragover", event => dragOver(event, square));
    button.addEventListener("drop", event => dropPiece(event, square));
    button.addEventListener("dragend", endDrag);
    boardElement.append(button);
  });
}

function canInteract() {
  return game && !busy && game.status === "playing" && game.turn === game.human_color;
}

async function clickSquare(square) {
  if (!canInteract()) return;
  if (!selected) {
    if (legalFrom(square).length) selected = square;
    renderBoard();
    return;
  }
  if (!legalFrom(selected).some(move => move.slice(2, 4) === square)) {
    selected = legalFrom(square).length ? square : null;
    renderBoard();
    return;
  }
  await movePiece(selected, square);
}

async function movePiece(from, to) {
  const candidates = legalFrom(from).filter(move => move.slice(2, 4) === to);
  if (!candidates.length) return;
  let move = candidates[0];
  if (candidates.length > 1) {
    const piece = await choosePromotion();
    if (!piece) return;
    move = candidates.find(candidate => candidate.endsWith(piece));
  }
  selected = null;
  await send(`/api/games/${game.id}/moves`, {move, ply: game.moves.length});
  if (game && game.status === "playing" && game.turn === game.jev_color) await requestJev();
}

function startDrag(event, square) {
  if (!canInteract() || !legalFrom(square).length) {
    event.preventDefault();
    return;
  }
  selected = square;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", square);
  event.currentTarget.classList.add("dragging", "selected");
  for (const move of legalFrom(square)) {
    boardElement.querySelector(`[data-square="${move.slice(2, 4)}"]`)?.classList.add("target");
  }
}

function dragOver(event, square) {
  if (selected && legalFrom(selected).some(move => move.slice(2, 4) === square)) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }
}

function dropPiece(event, square) {
  event.preventDefault();
  const from = event.dataTransfer.getData("text/plain") || selected;
  movePiece(from, square);
}

function endDrag() {
  selected = null;
  renderBoard();
}

function choosePromotion() {
  return new Promise(resolve => {
    const finish = () => {
      promotionDialog.removeEventListener("close", finish);
      resolve(promotionDialog.returnValue || null);
    };
    promotionDialog.addEventListener("close", finish);
    promotionDialog.showModal();
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: options.body ? {"Content-Type": "application/json"} : {},
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

async function send(path, body) {
  busy = true;
  render();
  try {
    game = await api(path, {method: "POST", body});
    receivedAt = performance.now();
    jevError = null;
    retryButton.hidden = true;
  } catch (error) {
    statusElement.textContent = error.message;
  } finally {
    busy = false;
    render();
  }
}

async function requestJev(run = runNumber) {
  if (!game || run !== runNumber) return;
  const gameId = game.id;
  busy = true;
  retryButton.hidden = true;
  render();
  try {
    const next = await api(`/api/games/${gameId}/jev`, {method: "POST", body: {ply: game.moves.length}});
    if (run !== runNumber) return;
    game = next;
    receivedAt = performance.now();
    jevError = null;
  } catch (error) {
    if (run !== runNumber) return;
    jevError = error.message;
    retryButton.hidden = false;
  } finally {
    if (run !== runNumber) return;
    busy = false;
    render();
    if (!jevError && game.mode === "jev-vs-jev" && game.status === "playing") {
      requestJev(run);
    }
  }
}

async function refreshGame() {
  if (!game || busy) return;
  busy = true;
  try {
    game = await api(`/api/games/${game.id}`);
    receivedAt = performance.now();
  } finally {
    busy = false;
    render();
  }
}

function formatClock(seconds) {
  const safe = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

function currentClock(color) {
  let seconds = game.clocks[color];
  if (game.status === "playing" && game.turn === color) seconds -= (performance.now() - receivedAt) / 1000;
  return Math.max(0, seconds);
}

function renderPlayers() {
  const spectator = game.mode === "jev-vs-jev";
  const topColor = spectator ? "black" : (game.human_color === "white" ? "black" : "white");
  const bottomColor = spectator ? "white" : game.human_color;
  [["#top-player", topColor], ["#bottom-player", bottomColor]].forEach(([selector, color]) => {
    const element = document.querySelector(selector);
    const seconds = currentClock(color);
    element.querySelector(".name").textContent = spectator ? `${color === "white" ? "White" : "Black"} Jev` : (color === game.human_color ? "You" : "Jev");
    element.querySelector(".clock").textContent = formatClock(seconds);
    element.querySelector(".clock").classList.toggle("low", seconds < 30);
    element.classList.toggle("active", game.status === "playing" && game.turn === color);
  });
}

function renderMoves() {
  const list = document.querySelector("#move-list");
  list.replaceChildren();
  for (let index = 0; index < game.moves.length; index += 2) {
    const item = document.createElement("li");
    item.innerHTML = `<span class="move-pair"><span>${game.moves[index].san}</span><span>${game.moves[index + 1]?.san || ""}</span></span>`;
    list.append(item);
  }
  list.scrollTop = list.scrollHeight;
}

function renderStatus() {
  const spectator = game.mode === "jev-vs-jev";
  let status;
  if (jevError) status = jevError;
  else if (game.status === "finished") status = `${game.result} — ${game.termination}`;
  else if (spectator && busy) status = `${game.turn === "white" ? "White" : "Black"} Jev is thinking`;
  else if (spectator) status = `${game.turn === "white" ? "White" : "Black"} Jev to move`;
  else if (busy && game.turn === game.jev_color) status = "Jev is thinking";
  else if (game.turn === game.human_color) status = game.in_check ? "Your king is in check" : "Your move";
  else status = "Jev to move";
  statusElement.textContent = status;
  document.querySelector("#game-state").textContent = game.status === "finished" ? game.result : "In progress";
  document.querySelector("#claim-draw").disabled = busy || !game.can_claim_draw || game.turn !== game.human_color;
  document.querySelector("#resign").disabled = busy || game.status === "finished";
  document.querySelector(".actions").hidden = spectator;
}

function render() {
  if (!game) return;
  renderBoard();
  renderPlayers();
  renderMoves();
  renderStatus();
}

async function start(color, mode) {
  const run = ++runNumber;
  busy = true;
  game = await api("/api/games", {method: "POST", body: mode ? {mode} : {color}});
  receivedAt = performance.now();
  jevError = null;
  welcomeElement.hidden = true;
  gameElement.hidden = false;
  busy = false;
  render();
  if (game.mode === "jev-vs-jev" || game.turn === game.jev_color) await requestJev(run);
}

document.querySelectorAll("[data-color], [data-mode]").forEach(button => button.addEventListener("click", () => start(button.dataset.color, button.dataset.mode)));
document.querySelector("#new-game").addEventListener("click", () => {
  runNumber += 1;
  game = null;
  selected = null;
  jevError = null;
  busy = false;
  gameElement.hidden = true;
  welcomeElement.hidden = false;
});
document.querySelector("#resign").addEventListener("click", async () => {
  if (confirm("Resign this game?")) await send(`/api/games/${game.id}/resign`, {});
});
document.querySelector("#claim-draw").addEventListener("click", () => send(`/api/games/${game.id}/draw`, {}));
retryButton.addEventListener("click", requestJev);

setInterval(() => {
  if (!game) return;
  renderPlayers();
  if (game.status === "playing" && currentClock(game.turn) === 0) refreshGame();
}, 250);
