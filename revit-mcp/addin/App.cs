using System;
using Autodesk.Revit.UI;

namespace RevitMcp
{
    /// <summary>
    /// Revit entry point. Starts a local HTTP bridge (127.0.0.1 only) when Revit starts,
    /// so the MCP server can send commands that are executed inside Revit's API context.
    /// </summary>
    public class App : IExternalApplication
    {
        public const int DefaultPort = 8765;

        private BridgeServer _server;

        public Result OnStartup(UIControlledApplication application)
        {
            try
            {
                int port = DefaultPort;
                string env = Environment.GetEnvironmentVariable("REVIT_MCP_PORT");
                if (!string.IsNullOrEmpty(env) && int.TryParse(env, out int p)) port = p;

                var handler = new CommandHandler();
                var externalEvent = ExternalEvent.Create(handler);
                _server = new BridgeServer(port, handler, externalEvent);
                _server.Start();
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                TaskDialog.Show("Revit MCP", "Failed to start MCP bridge:\n" + ex.Message);
                return Result.Failed;
            }
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            _server?.Stop();
            return Result.Succeeded;
        }
    }
}
