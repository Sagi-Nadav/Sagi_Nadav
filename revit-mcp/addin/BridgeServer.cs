using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.Revit.UI;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace RevitMcp
{
    /// <summary>A command waiting to run on Revit's main thread.</summary>
    public class PendingCommand
    {
        public string Name;
        public JObject Args;
        public TaskCompletionSource<JToken> Result =
            new TaskCompletionSource<JToken>(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    /// <summary>
    /// Minimal HTTP server bound to 127.0.0.1. Protocol:
    ///   GET  /ping                      -> {"ok":true}
    ///   POST /command  {"command": "...", "args": {...}}
    ///        -> {"ok":true,"result":...} or {"ok":false,"error":"..."}
    /// Every command is handed to Revit through an ExternalEvent, because the
    /// Revit API may only be called from Revit's own thread.
    /// </summary>
    public class BridgeServer
    {
        private readonly int _port;
        private readonly CommandHandler _handler;
        private readonly ExternalEvent _event;
        private HttpListener _listener;
        private Thread _thread;
        private volatile bool _running;

        public static readonly TimeSpan CommandTimeout = TimeSpan.FromSeconds(120);

        public BridgeServer(int port, CommandHandler handler, ExternalEvent externalEvent)
        {
            _port = port;
            _handler = handler;
            _event = externalEvent;
        }

        public void Start()
        {
            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{_port}/");
            _listener.Start();
            _running = true;
            _thread = new Thread(Loop) { IsBackground = true, Name = "RevitMcpBridge" };
            _thread.Start();
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); _listener?.Close(); } catch { }
        }

        private void Loop()
        {
            while (_running)
            {
                HttpListenerContext ctx;
                try { ctx = _listener.GetContext(); }
                catch { if (!_running) return; continue; }
                Task.Run(() => Handle(ctx));
            }
        }

        private void Handle(HttpListenerContext ctx)
        {
            JObject response;
            try
            {
                string path = ctx.Request.Url.AbsolutePath.TrimEnd('/');
                if (ctx.Request.HttpMethod == "GET" && path == "/ping")
                {
                    response = new JObject { ["ok"] = true, ["service"] = "revit-mcp" };
                }
                else if (ctx.Request.HttpMethod == "POST" && path == "/command")
                {
                    string body;
                    using (var reader = new StreamReader(ctx.Request.InputStream, Encoding.UTF8))
                        body = reader.ReadToEnd();
                    var json = JObject.Parse(body);
                    var cmd = new PendingCommand
                    {
                        Name = (string)json["command"],
                        Args = json["args"] as JObject ?? new JObject()
                    };
                    if (string.IsNullOrEmpty(cmd.Name)) throw new ArgumentException("Missing 'command'.");

                    _handler.Queue.Enqueue(cmd);
                    var raise = _event.Raise();
                    if (raise != ExternalEventRequest.Accepted && raise != ExternalEventRequest.Pending)
                        throw new InvalidOperationException("Revit refused the request: " + raise);

                    if (!cmd.Result.Task.Wait(CommandTimeout))
                        throw new TimeoutException(
                            "Revit did not respond in time. Close any open dialog in Revit and try again.");

                    response = new JObject { ["ok"] = true, ["result"] = cmd.Result.Task.Result };
                }
                else
                {
                    ctx.Response.StatusCode = 404;
                    response = new JObject { ["ok"] = false, ["error"] = "Not found" };
                }
            }
            catch (Exception ex)
            {
                var inner = ex is AggregateException ae && ae.InnerException != null ? ae.InnerException : ex;
                response = new JObject { ["ok"] = false, ["error"] = inner.Message };
            }

            try
            {
                byte[] bytes = Encoding.UTF8.GetBytes(response.ToString(Formatting.None));
                ctx.Response.ContentType = "application/json; charset=utf-8";
                ctx.Response.ContentLength64 = bytes.Length;
                ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
                ctx.Response.OutputStream.Close();
            }
            catch { }
        }
    }

    /// <summary>Runs queued commands on Revit's main thread.</summary>
    public class CommandHandler : IExternalEventHandler
    {
        public readonly ConcurrentQueue<PendingCommand> Queue = new ConcurrentQueue<PendingCommand>();

        public void Execute(UIApplication app)
        {
            while (Queue.TryDequeue(out var cmd))
            {
                try
                {
                    cmd.Result.TrySetResult(Commands.Dispatch(app, cmd.Name, cmd.Args));
                }
                catch (Exception ex)
                {
                    cmd.Result.TrySetException(ex);
                }
            }
        }

        public string GetName() => "Revit MCP command handler";
    }
}
