#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;

use tauri::{Emitter, Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct BackendState {
    child: Mutex<Option<CommandChild>>,
    port: u16,
}

async fn spawn_backend(app: &tauri::AppHandle, state: &BackendState) -> Result<String, String> {
    let mut guard = state.child.lock().map_err(|_| "Failed to lock backend child state")?;
    if guard.is_some() {
        return Ok(format!("http://127.0.0.1:{}", state.port));
    }

    let sidecar = app
        .shell()
        .sidecar("agentpm-api")
        .map_err(|err| err.to_string())?
        .args(["serve", "--port", &state.port.to_string()]);

    let (mut rx, child) = sidecar.spawn().map_err(|err| err.to_string())?;
    *guard = Some(child);

    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let message = String::from_utf8_lossy(&line).to_string();
                    let _ = app_handle.emit("backend-log", message);
                }
                CommandEvent::Stderr(line) => {
                    let message = String::from_utf8_lossy(&line).to_string();
                    let _ = app_handle.emit("backend-log", message);
                }
                _ => {}
            }
        }
    });

    Ok(format!("http://127.0.0.1:{}", state.port))
}

#[tauri::command]
async fn ensure_backend(app: tauri::AppHandle, state: State<'_, BackendState>) -> Result<String, String> {
    spawn_backend(&app, &state).await
}

#[tauri::command]
async fn stop_backend(state: State<'_, BackendState>) -> Result<(), String> {
    let mut guard = state.child.lock().map_err(|_| "Failed to lock backend child state")?;
    if let Some(child) = guard.as_mut() {
        child.kill().map_err(|err| err.to_string())?;
    }
    *guard = None;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState {
            child: Mutex::new(None),
            port: 8765,
        })
        .invoke_handler(tauri::generate_handler![ensure_backend, stop_backend])
        .setup(|app| {
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Some(state) = handle.try_state::<BackendState>() {
                    let _ = spawn_backend(&handle, state.inner()).await;
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
