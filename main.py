def _render_expired(plan, reason):
    ...
    with ui.column().classes(...):
        ...
            ui.button("Log out",
                      on_click=lambda: ui.navigate.to("/logout")).style(
                "background:#161616;color:#e8e8e8;"
                "border:1px solid #262626;border-radius:3px;"
                "padding:0 22px;min-height:40px;font-size:12px;"
                "text-transform:none;")
