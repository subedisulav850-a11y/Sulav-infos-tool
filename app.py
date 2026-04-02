from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import json
from Utilities.until import load_accounts
from Api.Account import get_garena_token, get_major_login
from Api.InGame import get_player_personal_show, get_player_stats, search_account_by_keyword

accounts = load_accounts()

SERVER_PRIORITY = ["IND", "BD", "PK", "SG", "ID", "TH", "VN", "US", "TW", "ME", "BR", "RU", "CIS"]

CREDITS = {
    "_tool": "SULAV info tool",
    "_channel": "@sulav_codex_ff",
    "_developer": "@sulav_don2"
}

app = Flask(__name__)
CORS(app)


# ── Inject credits into every JSON response ────────────────────────────────────
@app.after_request
def inject_credits(response):
    if 'application/json' in response.content_type:
        try:
            data = json.loads(response.get_data(as_text=True))
            if isinstance(data, dict):
                data.update(CREDITS)
                response.set_data(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            pass
    return response


# ── Helpers ───────────────────────────────────────────────────────────────────
def authenticate_server(server):
    if server not in accounts:
        return None, None
    auth = get_garena_token(accounts[server]['uid'], accounts[server]['password'])
    if not auth or 'access_token' not in auth:
        return None, None
    login = get_major_login(auth["access_token"], auth["open_id"])
    if not login or 'token' not in login:
        return None, None
    return login["token"], login["serverUrl"]


def auto_detect_server(uid, mode="personal_show"):
    for server in SERVER_PRIORITY:
        try:
            token, server_url = authenticate_server(server)
            if not token:
                continue
            if mode == "personal_show":
                result = get_player_personal_show(server_url, token, int(uid), False, 7)
                if result:
                    return server, token, server_url
            elif mode == "stats":
                result = get_player_stats(token, server_url, "br", uid, "CAREER")
                if result:
                    return server, token, server_url
        except Exception:
            continue
    return None, None, None


# ── Website ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html', servers=list(accounts.keys()))


# ── Clean Short Endpoints (no region needed) ───────────────────────────────────
@app.route('/info', methods=['GET'])
def info():
    """Auto-detect server and return full player profile. Just pass uid."""
    try:
        uid = request.args.get('uid', '').strip()
        server = request.args.get('server', 'AUTO').upper()
        if not uid:
            return jsonify({"success": False, "error": "uid parameter is required", "usage": "/info?uid=YOUR_UID"}), 400
        try:
            uid_int = int(uid)
            if uid_int <= 0:
                return jsonify({"success": False, "error": "uid must be a positive integer"}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "uid must be numeric"}), 400

        if server != 'AUTO' and server in accounts:
            token, server_url = authenticate_server(server)
            if not token:
                return jsonify({"success": False, "error": "Authentication failed for selected server"}), 401
            detected_server = server
        else:
            detected_server, token, server_url = auto_detect_server(uid_int, mode="personal_show")
            if not detected_server:
                return jsonify({"success": False, "error": "Player not found on any server", "uid": uid}), 404

        result = get_player_personal_show(server_url, token, uid_int, True, 7)
        if not result:
            return jsonify({"success": False, "error": "No player data found", "uid": uid}), 404

        return jsonify({"success": True, "uid": uid, "server": detected_server, "data": result}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/stats', methods=['GET'])
def stats():
    """Auto-detect server and return player stats. Just pass uid."""
    try:
        uid = request.args.get('uid', '').strip()
        gamemode = request.args.get('gamemode', 'br').lower()
        matchmode = request.args.get('matchmode', 'CAREER').upper()

        if not uid:
            return jsonify({"success": False, "error": "uid parameter is required", "usage": "/stats?uid=YOUR_UID&gamemode=br&matchmode=CAREER"}), 400
        if not uid.isdigit():
            return jsonify({"success": False, "error": "uid must be numeric"}), 400
        if gamemode not in ['br', 'cs']:
            return jsonify({"success": False, "error": "gamemode must be 'br' or 'cs'"}), 400
        if matchmode not in ['CAREER', 'NORMAL', 'RANKED']:
            return jsonify({"success": False, "error": "matchmode must be CAREER, NORMAL, or RANKED"}), 400

        server = request.args.get('server', 'AUTO').upper()
        if server != 'AUTO' and server in accounts:
            token, server_url = authenticate_server(server)
            if not token:
                return jsonify({"success": False, "error": "Authentication failed for selected server"}), 401
            detected_server = server
        else:
            detected_server, token, server_url = auto_detect_server(uid, mode="stats")
            if not detected_server:
                return jsonify({"success": False, "error": "Player not found on any server", "uid": uid}), 404

        player_stats = get_player_stats(token, server_url, gamemode, uid, matchmode)
        if not player_stats:
            return jsonify({"success": False, "error": "No stats found", "uid": uid}), 404

        return jsonify({"success": True, "uid": uid, "server": detected_server, "gamemode": gamemode, "matchmode": matchmode, "data": player_stats}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/search', methods=['GET'])
def search():
    """Search players by name. Pass name and server."""
    try:
        name = request.args.get('name', '').strip()
        server = request.args.get('server', 'IND').upper()

        if not name:
            return jsonify({"success": False, "error": "name parameter is required", "usage": "/search?name=PLAYER_NAME&server=IND"}), 400
        if len(name) < 3:
            return jsonify({"success": False, "error": "name must be at least 3 characters"}), 400
        if server not in accounts:
            return jsonify({"success": False, "error": f"Invalid server. Available: {list(accounts.keys())}"}), 400

        token, server_url = authenticate_server(server)
        if not token:
            return jsonify({"success": False, "error": "Authentication failed"}), 401

        results = search_account_by_keyword(server_url, token, name)
        return jsonify({"success": True, "server": server, "name": name, "results": results}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Health & Servers ──────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "online",
        "servers_configured": len(accounts),
        "version": "2.0.0"
    }), 200


@app.route('/get_servers', methods=['GET'])
def get_servers():
    return jsonify({
        "success": True,
        "servers": list(accounts.keys()),
        "total": len(accounts)
    }), 200


# ── Get Player by UID (auto or manual server) ─────────────────────────────────
@app.route('/get_player_info', methods=['GET'])
def get_player_info():
    try:
        uid = request.args.get('uid')
        server = request.args.get('server', 'AUTO').upper()

        if not uid:
            return jsonify({"success": False, "error": "UID parameter is required"}), 400
        try:
            uid_int = int(uid)
            if uid_int <= 0:
                return jsonify({"success": False, "error": "UID must be a positive integer"}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "UID must be numeric"}), 400

        if server == 'AUTO':
            detected_server, token, server_url = auto_detect_server(uid_int, mode="personal_show")
            if not detected_server:
                return jsonify({"success": False, "error": "Could not detect server for this UID"}), 404
        else:
            if server not in accounts:
                return jsonify({"success": False, "error": f"Invalid server: {server}"}), 400
            token, server_url = authenticate_server(server)
            if not token:
                return jsonify({"success": False, "error": "Authentication failed"}), 401
            detected_server = server

        result = get_player_personal_show(server_url, token, uid_int, True, 7)
        if not result:
            return jsonify({"success": False, "error": "No player data found for this UID"}), 404

        return jsonify({"success": True, "detected_server": detected_server, "uid": uid, "data": result}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Get Player Stats (auto or manual server) ──────────────────────────────────
@app.route('/get_player_stats_auto', methods=['GET'])
def get_player_stats_auto():
    try:
        uid = request.args.get('uid')
        gamemode = request.args.get('gamemode', 'br').lower()
        matchmode = request.args.get('matchmode', 'CAREER').upper()
        server = request.args.get('server', 'AUTO').upper()

        if not uid:
            return jsonify({"success": False, "error": "UID parameter is required"}), 400
        if not uid.isdigit():
            return jsonify({"success": False, "error": "UID must be numeric"}), 400
        if gamemode not in ['br', 'cs']:
            return jsonify({"success": False, "error": "Gamemode must be 'br' or 'cs'"}), 400
        if matchmode not in ['CAREER', 'NORMAL', 'RANKED']:
            return jsonify({"success": False, "error": "Matchmode must be CAREER, NORMAL, or RANKED"}), 400

        if server == 'AUTO':
            detected_server, token, server_url = auto_detect_server(uid, mode="stats")
            if not detected_server:
                return jsonify({"success": False, "error": "Could not detect server for this UID"}), 404
        else:
            if server not in accounts:
                return jsonify({"success": False, "error": f"Invalid server: {server}"}), 400
            token, server_url = authenticate_server(server)
            if not token:
                return jsonify({"success": False, "error": "Authentication failed"}), 401
            detected_server = server

        stats = get_player_stats(token, server_url, gamemode, uid, matchmode)
        if not stats:
            return jsonify({"success": False, "error": "No stats found"}), 404

        return jsonify({
            "success": True,
            "detected_server": detected_server,
            "uid": uid,
            "gamemode": gamemode,
            "matchmode": matchmode,
            "data": stats
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Full Profile (auto) ───────────────────────────────────────────────────────
@app.route('/get_player_full_profile', methods=['GET'])
def get_player_full_profile():
    try:
        uid = request.args.get('uid')
        server = request.args.get('server', 'AUTO').upper()

        if not uid:
            return jsonify({"success": False, "error": "UID parameter is required"}), 400
        try:
            uid_int = int(uid)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "UID must be numeric"}), 400

        if server == 'AUTO':
            detected_server, token, server_url = auto_detect_server(uid_int, mode="personal_show")
            if not detected_server:
                return jsonify({"success": False, "error": "Could not detect server"}), 404
        else:
            if server not in accounts:
                return jsonify({"success": False, "error": f"Invalid server: {server}"}), 400
            token, server_url = authenticate_server(server)
            if not token:
                return jsonify({"success": False, "error": "Authentication failed"}), 401
            detected_server = server

        profile = get_player_personal_show(server_url, token, uid_int, True, 7)
        br_stats, cs_stats = None, None
        try:
            br_stats = get_player_stats(token, server_url, "br", uid, "CAREER")
        except Exception:
            pass
        try:
            cs_stats = get_player_stats(token, server_url, "cs", uid, "CAREER")
        except Exception:
            pass

        return jsonify({
            "success": True,
            "detected_server": detected_server,
            "uid": uid,
            "profile": profile,
            "br_stats": br_stats,
            "cs_stats": cs_stats
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Search by Nickname ────────────────────────────────────────────────────────
@app.route('/search_by_nickname', methods=['GET'])
def search_by_nickname():
    try:
        nickname = request.args.get('nickname', '').strip()
        server = request.args.get('server', 'IND').upper()

        if not nickname:
            return jsonify({"success": False, "error": "Nickname parameter is required"}), 400
        if len(nickname) < 3:
            return jsonify({"success": False, "error": "Nickname must be at least 3 characters"}), 400
        if server not in accounts:
            return jsonify({"success": False, "error": f"Invalid server: {server}"}), 400

        token, server_url = authenticate_server(server)
        if not token:
            return jsonify({"success": False, "error": "Authentication failed"}), 401

        results = search_account_by_keyword(server_url, token, nickname)
        return jsonify({
            "success": True,
            "server": server,
            "keyword": nickname,
            "results": results
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Get Player by Nickname (auto-fetch first result) ──────────────────────────
@app.route('/get_player_by_nickname', methods=['GET'])
def get_player_by_nickname():
    try:
        nickname = request.args.get('nickname', '').strip()
        server = request.args.get('server', 'IND').upper()

        if not nickname:
            return jsonify({"success": False, "error": "Nickname parameter is required"}), 400
        if len(nickname) < 3:
            return jsonify({"success": False, "error": "Nickname must be at least 3 characters"}), 400
        if server not in accounts:
            return jsonify({"success": False, "error": f"Invalid server: {server}"}), 400

        token, server_url = authenticate_server(server)
        if not token:
            return jsonify({"success": False, "error": "Authentication failed"}), 401

        search_results = search_account_by_keyword(server_url, token, nickname)

        # Extract accounts list from result
        account_list = []
        if isinstance(search_results, dict):
            for key in ('accountInfos', 'accountInfo', 'accounts', 'players'):
                if key in search_results:
                    account_list = search_results[key]
                    break
            if not account_list and 'accountId' in search_results:
                account_list = [search_results]
        elif isinstance(search_results, list):
            account_list = search_results

        if not account_list:
            return jsonify({"success": False, "error": "No players found with that nickname"}), 404

        first = account_list[0]
        uid = first.get('accountId') or first.get('uid') or first.get('id')

        profile = None
        if uid:
            try:
                profile = get_player_personal_show(server_url, token, int(uid), True, 7)
            except Exception:
                pass

        return jsonify({
            "success": True,
            "server": server,
            "search_results": account_list,
            "top_match": first,
            "top_match_profile": profile
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Original endpoints (kept) ─────────────────────────────────────────────────
@app.route('/get_search_account_by_keyword', methods=['GET'])
def get_search_account_by_keyword():
    try:
        region = request.args.get('server', 'IND').upper()
        search_term = request.args.get('keyword')
        if not search_term:
            return jsonify({"success": False, "error": "Keyword parameter is required"}), 400
        if len(search_term.strip()) < 3:
            return jsonify({"success": False, "error": "Keyword must be at least 3 characters"}), 400
        if region not in accounts:
            return jsonify({"success": False, "error": f"Invalid server: {region}"}), 400
        auth_response = get_garena_token(accounts[region]['uid'], accounts[region]['password'])
        if not auth_response or 'access_token' not in auth_response:
            return jsonify({"success": False, "error": "Authentication failed"}), 401
        login_response = get_major_login(auth_response["access_token"], auth_response["open_id"])
        if not login_response or 'token' not in login_response:
            return jsonify({"success": False, "error": "Major login failed"}), 401
        search_results = search_account_by_keyword(login_response["serverUrl"], login_response["token"], search_term)
        return jsonify({"success": True, "data": search_results}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/get_player_stats', methods=['GET'])
def get_player_stat():
    try:
        server = request.args.get('server', 'IND').upper()
        uid = request.args.get('uid')
        gamemode = request.args.get('gamemode', 'br').lower()
        matchmode = request.args.get('matchmode', 'CAREER').upper()
        if not uid:
            return jsonify({"success": False, "error": "UID parameter is required"}), 400
        if not uid.isdigit():
            return jsonify({"success": False, "error": "UID must be numeric"}), 400
        if server not in accounts:
            return jsonify({"success": False, "error": f"Server '{server}' not found"}), 400
        if gamemode not in ['br', 'cs']:
            return jsonify({"success": False, "error": "Gamemode must be 'br' or 'cs'"}), 400
        if matchmode not in ['CAREER', 'NORMAL', 'RANKED']:
            return jsonify({"success": False, "error": "Matchmode must be CAREER, NORMAL, or RANKED"}), 400
        auth = get_garena_token(accounts[server]['uid'], accounts[server]['password'])
        if not auth or 'access_token' not in auth:
            return jsonify({"success": False, "error": "Garena authentication failed"}), 401
        login = get_major_login(auth["access_token"], auth["open_id"])
        if not login or 'token' not in login:
            return jsonify({"success": False, "error": "Major login failed"}), 401
        stats = get_player_stats(login["token"], login["serverUrl"], gamemode, uid, matchmode)
        if not stats:
            return jsonify({"success": False, "error": "No stats found"}), 404
        return jsonify({"success": True, "data": stats, "metadata": {"server": server, "uid": uid, "gamemode": gamemode, "matchmode": matchmode}}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/get_player_personal_show', methods=['GET'])
def get_account_info():
    try:
        server = request.args.get('server', 'IND').upper()
        uid = request.args.get('uid')
        need_gallery_info = request.args.get('need_gallery_info', False)
        call_sign_src = request.args.get('call_sign_src', 7)
        if not uid:
            return jsonify({"success": False, "error": "UID parameter is required"}), 400
        try:
            uid_int = int(uid)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "UID must be numeric"}), 400
        if server not in accounts:
            return jsonify({"success": False, "error": f"Server '{server}' not found"}), 400
        try:
            if isinstance(need_gallery_info, str):
                need_gallery_info = need_gallery_info.lower() in ['true', '1', 'yes']
            need_gallery_info = bool(need_gallery_info)
        except Exception:
            need_gallery_info = False
        try:
            call_sign_src_int = int(call_sign_src)
        except Exception:
            call_sign_src_int = 7
        auth = get_garena_token(accounts[server]['uid'], accounts[server]['password'])
        if not auth or 'access_token' not in auth:
            return jsonify({"success": False, "error": "Garena authentication failed"}), 401
        login = get_major_login(auth["access_token"], auth["open_id"])
        if not login or 'serverUrl' not in login or 'token' not in login:
            return jsonify({"success": False, "error": "Major login failed"}), 401
        result = get_player_personal_show(login["serverUrl"], login["token"], uid_int, need_gallery_info, call_sign_src_int)
        if not result:
            return jsonify({"success": False, "error": f"No player data found for UID: {uid_int}"}), 404
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
