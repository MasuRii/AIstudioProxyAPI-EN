/**
 * LogViewer Component
 * Real-time log viewer that connects to WebSocket for live log streaming
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Pause, Play, Download, Trash2 } from 'lucide-react';
import { useI18n } from '@/contexts';
import styles from './LogViewer.module.css';

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  message: string;
}

export function LogViewer() {
  const { t } = useI18n();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pausedLogsRef = useRef<LogEntry[]>([]);

  const scrollToBottom = useCallback(() => {
    if (logContainerRef.current && !isPaused) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [isPaused]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
    
    const connect = () => {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const entry: LogEntry = {
            id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            timestamp: data.timestamp || new Date().toISOString(),
            level: data.level || 'INFO',
            message: data.message || event.data,
          };

          if (isPaused) {
            pausedLogsRef.current.push(entry);
          } else {
            setLogs(prev => {
              const newLogs = [...prev, entry];
              // Keep last 500 logs to prevent memory issues
              return newLogs.slice(-500);
            });
          }
        } catch {
          // Handle plain text messages
          const entry: LogEntry = {
            id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            timestamp: new Date().toISOString(),
            level: 'INFO',
            message: event.data,
          };
          
          if (isPaused) {
            pausedLogsRef.current.push(entry);
          } else {
            setLogs(prev => [...prev, entry].slice(-500));
          }
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        // Attempt to reconnect after 3 seconds
        setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        setIsConnected(false);
      };
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isPaused]);

  useEffect(() => {
    scrollToBottom();
  }, [logs, scrollToBottom]);

  const togglePause = () => {
    if (isPaused) {
      // Resume: add paused logs
      setLogs(prev => [...prev, ...pausedLogsRef.current].slice(-500));
      pausedLogsRef.current = [];
    }
    setIsPaused(!isPaused);
  };

  const clearLogs = () => {
    setLogs([]);
    pausedLogsRef.current = [];
  };

  const downloadLogs = () => {
    const content = logs
      .map(log => `[${log.timestamp}] [${log.level}] ${log.message}`)
      .join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getLevelClass = (level: LogEntry['level']) => {
    switch (level) {
      case 'DEBUG': return styles.debug;
      case 'INFO': return styles.info;
      case 'WARNING': return styles.warning;
      case 'ERROR': return styles.error;
      case 'CRITICAL': return styles.critical;
      default: return styles.info;
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <button
          className={`${styles.toolButton} ${isPaused ? styles.paused : ''}`}
          onClick={togglePause}
          title={isPaused ? t.logs.resumeStream : t.logs.pauseStream}
        >
          {isPaused ? <Play size={16} /> : <Pause size={16} />}
        </button>
        <button
          className={styles.toolButton}
          onClick={downloadLogs}
          title={t.logs.downloadLogs}
          disabled={logs.length === 0}
        >
          <Download size={16} />
        </button>
        <button
          className={styles.toolButton}
          onClick={clearLogs}
          title={t.logs.clearLogs}
          disabled={logs.length === 0}
        >
          <Trash2 size={16} />
        </button>
        <div className={`${styles.connectionStatus} ${isConnected ? styles.connected : ''}`}>
          <span className={styles.statusDot} />
        </div>
      </div>

      {isPaused && (
        <div className={styles.pausedBanner}>
          {t.logs.pausedMessage}
        </div>
      )}

      <div className={styles.logContainer} ref={logContainerRef}>
        {logs.length === 0 ? (
          <div className={styles.emptyState}>
            {isConnected ? t.logs.waitingForLogs : t.logs.connectingToServer}
          </div>
        ) : (
          logs.map(log => (
            <div key={log.id} className={styles.logEntry}>
              <span className={styles.timestamp}>
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span className={`${styles.level} ${getLevelClass(log.level)}`}>
                {log.level}
              </span>
              <span className={styles.message}>{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
