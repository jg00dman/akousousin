// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 John Goodman
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const xml = `<node><interface name="org.akousousin.FocusWindow">
    <method name="Current"><arg type="s" direction="out"/><arg type="u" direction="out"/></method>
    <signal name="Changed"><arg type="s"/><arg type="u"/></signal>
</interface></node>`;

export default class AkousousinFocus extends Extension {
    enable() {
        this._epoch = 0;
        this._instance = GLib.uuid_string_random();
        this._object = Gio.DBusExportedObject.wrapJSObject(xml, this);
        this._object.export(Gio.DBus.session, '/org/akousousin/FocusWindow');
        this._watch = global.display.connect('notify::focus-window', () => {
            this._epoch++;
            this._object.emit_signal('Changed', new GLib.Variant('(su)', this.Current()));
        });
    }

    Current() {
        const win = global.display.focus_window;
        const id = win && win.get_window_type() === Meta.WindowType.NORMAL
            ? this._instance + '/' + win.get_stable_sequence() : '';
        return [id, this._epoch];
    }

    disable() {
        global.display.disconnect(this._watch);
        this._object.emit_signal('Changed', new GLib.Variant('(su)', ['', ++this._epoch]));
        this._object.unexport();
        this._object = null;
    }
}
