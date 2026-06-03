import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook to fetch data from the MarketOS Flask API.
 * The API returns { status: "ok", ...data } on success
 * or { status: "error", message: "..." } on failure.
 * 
 * @param {string} endpoint - API endpoint path (e.g. '/api/status')
 * @param {number} refreshInterval - Auto-refresh interval in ms (default 30s)
 * @returns {{ data: any, loading: boolean, error: string|null, refetch: () => void }}
 */
export default function useApi(endpoint, refreshInterval = 30000) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(endpoint);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const json = await res.json();
      if (!mountedRef.current) return;

      // API returns { status: "ok", ...data } or { status: "error", message: "..." }
      if (json.status === 'error') {
        setError(json.message || 'Unknown API error');
      } else {
        // Remove meta fields, pass everything else as data
        const { status, timestamp, ...rest } = json;
        setData(rest);
        setError(null);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err.message || 'Failed to fetch data');
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [endpoint]);

  useEffect(() => {
    mountedRef.current = true;
    setLoading(true);
    setError(null);
    fetchData();

    if (refreshInterval > 0) {
      intervalRef.current = setInterval(fetchData, refreshInterval);
    }

    return () => {
      mountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData, refreshInterval]);

  return { data, loading, error, refetch: fetchData };
}
