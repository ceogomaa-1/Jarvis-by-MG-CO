'use client';
import { useState, useEffect, useRef, useMemo } from 'react';

const BOARD_COLS = 6;
const BOARD_ROWS = 10;

const TETRIS_PIECES = [
  { shape: [[1, 1, 1, 1]], color: 'bg-[#2d7ff9]' },
  { shape: [[1, 1], [1, 1]], color: 'bg-[#2d7ff9]' },
  { shape: [[0, 1, 0], [1, 1, 1]], color: 'bg-[#2d7ff9]/80' },
  { shape: [[1, 0], [1, 0], [1, 1]], color: 'bg-[#2d7ff9]/70' },
  { shape: [[0, 1, 1], [1, 1, 0]], color: 'bg-[#2d7ff9]/90' },
  { shape: [[1, 1, 0], [0, 1, 1]], color: 'bg-[#2d7ff9]/60' },
  { shape: [[0, 1], [0, 1], [1, 1]], color: 'bg-[#2d7ff9]/80' },
];

const CELL_SIZES = { sm: 10, md: 14, lg: 18 };
const TICK_SPEEDS = { fast: 110, normal: 260 };

function createEmptyBoard() {
  return Array.from({ length: BOARD_ROWS }, () => Array(BOARD_COLS).fill(null));
}

function isValidPosition(board, shape, x, y) {
  for (let r = 0; r < shape.length; r++) {
    for (let c = 0; c < shape[r].length; c++) {
      if (!shape[r][c]) continue;
      const nr = y + r;
      const nc = x + c;
      if (nr >= BOARD_ROWS || nc < 0 || nc >= BOARD_COLS) return false;
      if (nr >= 0 && board[nr][nc] !== null) return false;
    }
  }
  return true;
}

function lockPiece(board, shape, x, y, color) {
  const nb = board.map(row => [...row]);
  for (let r = 0; r < shape.length; r++) {
    for (let c = 0; c < shape[r].length; c++) {
      if (!shape[r][c]) continue;
      const nr = y + r;
      const nc = x + c;
      if (nr >= 0 && nr < BOARD_ROWS && nc >= 0 && nc < BOARD_COLS) {
        nb[nr][nc] = color;
      }
    }
  }
  return nb;
}

function clearLines(board) {
  const kept = board.filter(row => row.some(cell => cell === null));
  const cleared = BOARD_ROWS - kept.length;
  return [...Array.from({ length: cleared }, () => Array(BOARD_COLS).fill(null)), ...kept];
}

function spawnPiece() {
  const def = TETRIS_PIECES[Math.floor(Math.random() * TETRIS_PIECES.length)];
  const shape = def.shape;
  return {
    shape,
    color: def.color,
    x: Math.floor((BOARD_COLS - shape[0].length) / 2),
    y: 0,
  };
}

export default function TetrisLoader({
  size = 'sm',
  speed = 'fast',
  showLoadingText = true,
  loadingText = 'Loading...',
}) {
  const cellSize = CELL_SIZES[size] ?? 10;
  const tickSpeed = TICK_SPEEDS[speed] ?? 110;

  const boardRef = useRef(createEmptyBoard());
  const pieceRef = useRef(null);
  const [renderState, setRenderState] = useState(() => ({
    board: createEmptyBoard(),
    piece: null,
  }));

  useEffect(() => {
    const piece = spawnPiece();
    pieceRef.current = piece;
    setRenderState({ board: boardRef.current, piece });
  }, []);

  useEffect(() => {
    const tick = () => {
      const piece = pieceRef.current;
      if (!piece) return;

      const nextY = piece.y + 1;
      if (isValidPosition(boardRef.current, piece.shape, piece.x, nextY)) {
        const moved = { ...piece, y: nextY };
        pieceRef.current = moved;
        setRenderState({ board: boardRef.current, piece: moved });
      } else {
        const locked = lockPiece(boardRef.current, piece.shape, piece.x, piece.y, piece.color);
        const cleared = clearLines(locked);
        boardRef.current = cleared;

        const next = spawnPiece();
        if (!isValidPosition(cleared, next.shape, next.x, next.y)) {
          boardRef.current = createEmptyBoard();
        }
        pieceRef.current = next;
        setRenderState({ board: boardRef.current, piece: next });
      }
    };

    const id = setInterval(tick, tickSpeed);
    return () => clearInterval(id);
  }, [tickSpeed]);

  const displayBoard = useMemo(() => {
    const { board, piece } = renderState;
    const db = board.map(row => [...row]);
    if (piece) {
      for (let r = 0; r < piece.shape.length; r++) {
        for (let c = 0; c < piece.shape[r].length; c++) {
          if (!piece.shape[r][c]) continue;
          const row = piece.y + r;
          const col = piece.x + c;
          if (row >= 0 && row < BOARD_ROWS && col >= 0 && col < BOARD_COLS) {
            db[row][col] = piece.color;
          }
        }
      }
    }
    return db;
  }, [renderState]);

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className="border border-[rgba(232,232,232,0.1)] bg-transparent"
        style={{
          display: 'grid',
          gridTemplateRows: `repeat(${BOARD_ROWS}, ${cellSize}px)`,
          gridTemplateColumns: `repeat(${BOARD_COLS}, ${cellSize}px)`,
          gap: 1,
          padding: 4,
        }}
      >
        {displayBoard.flat().map((cell, i) => (
          <div
            key={i}
            className={`border border-[rgba(232,232,232,0.06)] ${cell ?? 'bg-[#0a0a0a]'}`}
            style={{ width: cellSize, height: cellSize }}
          />
        ))}
      </div>
      {showLoadingText && (
        <div className="text-[#e8e8e8]/50 text-[10px] font-mono tracking-widest uppercase">
          {loadingText}
        </div>
      )}
    </div>
  );
}
