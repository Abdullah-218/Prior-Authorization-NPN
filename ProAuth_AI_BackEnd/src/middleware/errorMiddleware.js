export function notFoundHandler(req, res, next) {
  res.status(404).json({ success: false, message: 'Route not found.' });
}

export function errorHandler(err, _req, res, next) {
  if (res.headersSent) {
    return next(err);
  }

  const status = err.status || 500;
  const message = status >= 500 ? 'Internal server error.' : err.message || 'Request failed.';

  // In development, print the error stack to the server console for debugging
  // Always log full error stack to server console to aid debugging
  // eslint-disable-next-line no-console
  console.error(err && err.stack ? err.stack : err);

  res.status(status).json({ success: false, message, errors: err.errors || [] });
}
