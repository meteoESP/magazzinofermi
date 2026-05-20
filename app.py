import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string

from flask import Flask, request, jsonify
from flask_cors import CORS
from auth import *
from database import db_functions as db

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})


EMAIL_MITTENTE = "kevin.dacco@fermi.mo.it"
PASSWORD_APP = "ipbe kbzi hjha wvax"


@app.route("/")
def home():
    return "Backend attivo"



@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    ruolo_richiesto = data.get("ruolo_richiesto", "professore")

    if not username or not password or not email:
        return jsonify({"error": "username, password ed email sono obbligatori"}), 400

    if db.registra_utente(username, password, email, ruolo=ruolo_richiesto):
        return jsonify({"message": "Registrazione inviata. Attendi approvazione da admin o tecnico."})
    return jsonify({"error": "Username già in uso"}), 400


@app.route("/login", methods=["POST"])
def login_route():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Credenziali mancanti"}), 400

    risultato = db.login(username, password)

    if risultato is None:
        return jsonify({"error": "Credenziali errate"}), 401
    if risultato == "non_approvato":
        return jsonify({"error": "Account in attesa di approvazione"}), 403

    token = genera_token(risultato["id"], risultato["username"], risultato["ruolo"])
    return jsonify({
        "token": token,
        "username": risultato["username"],
        "ruolo": risultato["ruolo"]
    })


@app.route("/cambia-password", methods=["POST"])
@tutti_gli_utenti
def cambia_password():
    data = request.json or {}
    vecchia = data.get("vecchia_password")
    nuova = data.get("nuova_password")
    utente_id = request.utente["user_id"]

    if not vecchia or not nuova:
        return jsonify({"error": "Fornisci vecchia e nuova password"}), 400

    if db.cambia_password(utente_id, vecchia, nuova):
        return jsonify({"message": "Password aggiornata"})
    return jsonify({"error": "Vecchia password errata"}), 400


@app.route("/recupero-password", methods=["POST"])
def recupero_password():
    data = request.json or {}
    email_destinatario = data.get("email")

    if not email_destinatario:
        return jsonify({"error": "Email mancante"}), 400

    try:
        conn = db.get_connection()
        utente = conn.execute("SELECT id, username FROM utenti WHERE email = ?", (email_destinatario,)).fetchone()

        if not utente:
            conn.close()
            return jsonify({"success": True, "message": "Se l'email esiste, riceverai le istruzioni."})

        username = utente[1]


        nuova_password_plain = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        password_criptata = hash_password(nuova_password_plain)
        conn.execute("UPDATE utenti SET password = ? WHERE email = ?", (password_criptata, email_destinatario))
        conn.commit()
        conn.close()


        if EMAIL_MITTENTE == "la.tua.email@gmail.com":
            print("=" * 50)
            print(f"⚠SIMULAZIONE RECUPERO PASSWORD")
            print(f"Email Destinatario: {email_destinatario}")
            print(f"Utente: {username}")
            print(f"NUOVA PASSWORD TEMPORANEA (USALA PER IL LOGIN): {nuova_password_plain}")
            print("=" * 50)
            return jsonify({'success': True, 'message': 'Simulazione completata. Controlla il terminale.'})

        msg = MIMEMultipart()
        msg['From'] = EMAIL_MITTENTE
        msg['To'] = email_destinatario
        msg['Subject'] = "FermiStock - Recupero Password"

        corpo_email = f"""
        <html>
            <body>
            <h2>Recupero Credenziali FermiStock</h2>
            <p>Ciao <b>{username}</b>,</p>
            <p>Hai richiesto il ripristino della tua password per il gestionale del laboratorio.</p>
            <p>La tua nuova password temporanea è: <b style="color:red; font-size:18px;">{nuova_password_plain}</b></p>
            <p>Ti consigliamo di accedere e cambiarla dal pannello il prima possibile.</p>
            </body>
        </html>
        """
        msg.attach(MIMEText(corpo_email, 'html'))


        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_MITTENTE, PASSWORD_APP)
        server.send_message(msg)
        server.quit()

        return jsonify({"success": True, "message": "Email inviata con successo"})

    except Exception as e:
        print("Errore recupero password:", e)
        return jsonify({"error": "Errore interno del server email"}), 500




@app.route("/utenti", methods=["GET"])
@solo_admin
def lista_utenti():
    return jsonify(db.get_tutti_utenti())


@app.route("/utenti", methods=["POST"])
@solo_admin
def crea_utente():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    ruolo = data.get("ruolo", "tecnico")

    if ruolo not in ("admin", "tecnico"):
        return jsonify({"error": "Usa /register per creare professori"}), 400

    if db.registra_utente(username, password, email, ruolo):
        conn = db.get_connection()
        conn.execute("UPDATE utenti SET approvato=1 WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return jsonify({"message": f"Utente {ruolo} creato e approvato"})
    return jsonify({"error": "Username già in uso"}), 400


@app.route("/utenti/<int:uid>/ruolo", methods=["PUT"])
@solo_admin
def cambia_ruolo(uid):
    data = request.json or {}
    nuovo_ruolo = data.get("ruolo")
    admin_id = request.utente["user_id"]

    if db.cambia_ruolo(uid, nuovo_ruolo, admin_id):
        return jsonify({"message": "Ruolo aggiornato"})
    return jsonify({"error": "Ruolo non valido"}), 400


@app.route("/utenti/<int:uid>", methods=["DELETE"])
@solo_admin
def elimina_utente(uid):
    admin_id = request.utente["user_id"]
    db.elimina_utente(uid, admin_id)
    return jsonify({"message": "Utente eliminato"})



@app.route("/utenti/in-attesa", methods=["GET"])
@admin_o_tecnico
def utenti_in_attesa():
    return jsonify(db.get_utenti_in_attesa())


@app.route("/utenti/<int:uid>/approva", methods=["POST"])
@admin_o_tecnico
def approva_utente(uid):
    approvatore_id = request.utente["user_id"]
    risultato = db.approva_utente(uid, approvatore_id)

    if risultato:
        if isinstance(risultato, dict):
            return jsonify(
                {"message": "Utente approvato.", "password_temporanea": risultato.get("password_temporanea")})
        return jsonify({"message": "Utente approvato."})

    return jsonify({"error": "Utente non trovato"}), 404



@app.route("/log", methods=["GET"])
@admin_o_tecnico
def get_log():
    uid = request.args.get("utente_id", type=int)
    limit = request.args.get("limit", default=100, type=int)
    return jsonify(db.get_log(filtro_utente_id=uid, limit=limit))


# ================================================================


@app.route("/componenti", methods=["GET"])
@tutti_gli_utenti
def lista_componenti():
    return jsonify(db.get_componenti())


@app.route("/componenti/<int:cid>", methods=["GET"])
@tutti_gli_utenti
def singolo_componente(cid):
    comp = db.get_componente(cid)
    if comp:
        return jsonify(comp)
    return jsonify({"error": "Non trovato"}), 404


@app.route("/componenti", methods=["POST"])
@admin_o_tecnico
def crea_componente():
    data = request.json or {}
    utente_id = request.utente["user_id"]

    if not data.get("nome"):
        return jsonify({"error": "Il nome è obbligatorio"}), 400

    try:
        db.aggiungi_componente(
            nome=data.get("nome"),
            famiglia=data.get("famiglia", ""),
            tipo=data.get("tipo", ""),
            ambito=data.get("ambito", ""),
            ambiente=data.get("ambiente", ""),
            sezione=data.get("sezione"),
            cassetto=data.get("cassetto", ""),
            quantita=data.get("quantita", 0),
            quantita_minima=data.get("quantita_minima", 0),
            quantita_generica=data.get("quantita_generica", ""),
            is_scorta=1 if data.get("is_scorta") else 0,
            datasheet=data.get("datasheet", ""),
            tag_ids=data.get("tag_ids", []),
            utente_id=utente_id
        )
        return jsonify({"message": "Componente aggiunto"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/componenti/<int:cid>", methods=["PUT"])
@admin_o_tecnico
def modifica_componente(cid):
    data = request.json or {}
    utente_id = request.utente["user_id"]
    try:
        db.aggiorna_componente(
            comp_id=cid,
            nome=data.get("nome"),
            famiglia=data.get("famiglia", ""),
            tipo=data.get("tipo", ""),
            ambito=data.get("ambito", ""),
            ambiente=data.get("ambiente", ""),
            sezione=data.get("sezione"),
            cassetto=data.get("cassetto", ""),
            quantita=data.get("quantita", 0),
            quantita_minima=data.get("quantita_minima", 0),
            quantita_generica=data.get("quantita_generica", ""),
            is_scorta=1 if data.get("is_scorta") else 0,
            datasheet=data.get("datasheet", ""),
            tag_ids=data.get("tag_ids", []),
            utente_id=utente_id
        )
        return jsonify({"message": "Componente aggiornato"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/componenti/<int:cid>", methods=["DELETE"])
@admin_o_tecnico
def elimina_componente(cid):
    utente_id = request.utente["user_id"]
    db.elimina_componente(cid, utente_id=utente_id)
    return jsonify({"message": "Componente eliminato"})



@app.route("/movimento", methods=["POST"])
@admin_o_tecnico
def movimento_route():
    data = request.json or {}
    utente_id = request.utente["user_id"]
    componente_id = data.get("componente_id")
    quantita = data.get("quantita")
    tipo = data.get("tipo")

    if tipo not in ("carico", "scarico"):
        return jsonify({"error": "tipo deve essere 'carico' o 'scarico'"}), 400

    db.movimento(componente_id, quantita, tipo, utente_id)
    return jsonify({"message": f"Movimento {tipo} registrato"})



@app.route("/scorte", methods=["GET"])
@admin_o_tecnico
def scorte():
    return jsonify(db.componenti_sotto_scorta())


@app.route("/elenchi", methods=["POST"])
@tutti_gli_utenti
def crea_elenco():
    data = request.json or {}
    utente_id = request.utente["user_id"]
    nome = data.get("nome")
    componenti = data.get("componenti", [])

    if not nome:
        return jsonify({"error": "Il nome è obbligatorio"}), 400

    elenco_id = db.crea_elenco(nome, utente_id)

    if componenti and isinstance(componenti, list):
        for comp in componenti:
            c_id = comp.get("id_componente")
            c_qty = comp.get("quantita")
            if c_id and c_qty:
                db.aggiungi_componente_a_elenco(elenco_id, c_id, c_qty)

    return jsonify({"id": elenco_id, "message": "Lista creata con successo"})


@app.route("/elenchi", methods=["GET"])
@tutti_gli_utenti
def lista_elenchi():
    elenchi = db.get_tutti_elenchi()

    try:
        conn = db.get_connection()
        for elenco in elenchi:
            if "componenti" not in elenco:
                cursor = conn.execute('''
                    SELECT c.id, c.nome, ec.quantita 
                    FROM elenco_componenti ec
                    JOIN componenti c ON ec.componente_id = c.id
                    WHERE ec.elenco_id = ?
                ''', (elenco["id"],))
                elenco["componenti"] = [{"id": r[0], "nome": r[1], "quantita": r[2]} for r in cursor.fetchall()]
        conn.close()
    except Exception as e:
        print("Errore arricchimento componenti:", e)

    return jsonify(elenchi)


@app.route("/elenchi/<int:eid>", methods=["DELETE"])
@tutti_gli_utenti
def elimina_elenco(eid):
    utente_id = request.utente["user_id"]
    ruolo = request.utente["ruolo"]

    try:
        conn = db.get_connection()
        cursor = conn.execute("SELECT creato_da FROM elenchi WHERE id=?", (eid,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Lista non trovata"}), 404

        if row[0] != utente_id and ruolo != "admin":
            conn.close()
            return jsonify({"error": "Non sei autorizzato a eliminare questa lista"}), 403

        conn.execute("DELETE FROM elenco_componenti WHERE elenco_id=?", (eid,))
        conn.execute("DELETE FROM elenchi WHERE id=?", (eid,))
        conn.commit()
        conn.close()

        return jsonify({"message": "Lista eliminata con successo"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/elenchi/<int:eid>", methods=["PUT"])
@tutti_gli_utenti
def modifica_elenco(eid):
    data = request.json or {}
    utente_id = request.utente["user_id"]
    ruolo = request.utente["ruolo"]

    nuovo_nome = data.get("nome")
    nuovi_componenti = data.get("componenti", [])

    if not nuovo_nome:
        return jsonify({"error": "Il nome è obbligatorio"}), 400

    try:
        conn = db.get_connection()
        cursor = conn.execute("SELECT creato_da FROM elenchi WHERE id=?", (eid,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Lista non trovata"}), 404

        if row[0] != utente_id and ruolo not in ["admin", "tecnico"]:
            conn.close()
            return jsonify({"error": "Non sei autorizzato a modificare questa lista"}), 403
        conn.execute("UPDATE elenchi SET nome = ? WHERE id = ?", (nuovo_nome, eid))
        conn.execute("DELETE FROM elenco_componenti WHERE elenco_id=?", (eid,))
        if nuovi_componenti and isinstance(nuovi_componenti, list):
            for comp in nuovi_componenti:
                c_id = comp.get("id_componente")
                c_qty = comp.get("quantita")
                if c_id and c_qty:
                    conn.execute(
                        "INSERT INTO elenco_componenti (elenco_id, componente_id, quantita) VALUES (?, ?, ?)",
                        (eid, c_id, c_qty)
                    )

        conn.commit()
        conn.close()

        return jsonify({"message": "Lista aggiornata con successo"})

    except Exception as e:
        print("Errore durante la modifica dell'elenco:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/elenchi/<int:eid>/verifica", methods=["GET"])
@tutti_gli_utenti
def verifica_elenco(eid):
    mancanti = db.verifica_disponibilita(eid)
    return jsonify(mancanti)


def gestisci_tabella_semplice(tabella):
    try:
        conn = db.get_connection()
        if request.method == "POST":
            if request.utente["ruolo"] == "professore":
                return jsonify({"error": "Non autorizzato"}), 403
            nome = request.json.get("nome")
            conn.execute(f"INSERT INTO {tabella} (nome) VALUES (?)", (nome,))
            conn.commit()
            conn.close()
            return jsonify({"message": f"Elemento aggiunto in {tabella}"})

        rows = conn.execute(f"SELECT * FROM {tabella}").fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify([]), 200


@app.route("/famiglie", methods=["GET", "POST"])
@tutti_gli_utenti
def route_famiglie():
    return gestisci_tabella_semplice("famiglie")


@app.route("/tipi", methods=["GET", "POST"])
@tutti_gli_utenti
def route_tipi():
    return gestisci_tabella_semplice("tipi")


@app.route("/ambiti", methods=["GET", "POST"])
@tutti_gli_utenti
def route_ambiti():
    return gestisci_tabella_semplice("ambiti")


@app.route("/tags", methods=["GET", "POST"])
@tutti_gli_utenti
def route_tags():
    return gestisci_tabella_semplice("tags")

def elimina_parametro(tabella, id_elemento):
    """Funzione generica per eliminare un elemento da una tabella di classificazione"""
    try:
        conn = db.get_connection()

        conn.execute(f"DELETE FROM {tabella} WHERE id = ?", (id_elemento,))
        conn.commit()
        conn.close()
        return jsonify({"message": f"Elemento eliminato da {tabella}"})
    except Exception as e:
        print(f"Errore eliminazione {tabella}:", e)
        return jsonify({"error": f"Impossibile eliminare l'elemento. Verifica che non sia in uso. Errore: {str(e)}"}), 500

@app.route("/famiglie/<int:id>", methods=["DELETE"])
@admin_o_tecnico
def delete_famiglia(id):
    return elimina_parametro("famiglie", id)

@app.route("/tipi/<int:id>", methods=["DELETE"])
@admin_o_tecnico
def delete_tipo(id):
    return elimina_parametro("tipi", id)

@app.route("/ambiti/<int:id>", methods=["DELETE"])
@admin_o_tecnico
def delete_ambito(id):
    return elimina_parametro("ambiti", id)

@app.route("/tags/<int:id>", methods=["DELETE"])
@admin_o_tecnico
def delete_tag(id):
    return elimina_parametro("tags", id)



@app.route("/acquisti", methods=["GET", "POST"])
@admin_o_tecnico
def gestisci_acquisti():
    try:
        conn = db.get_connection()
        conn.execute('''CREATE TABLE IF NOT EXISTS lista_acquisti (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        componente_id INTEGER,
                        quantita INTEGER,
                        note TEXT,
                        stato TEXT DEFAULT 'Da Acquistare',
                        FOREIGN KEY(componente_id) REFERENCES componenti(id))''')
        conn.commit()

        if request.method == "POST":
            data = request.json
            comp_id = data.get("componente_id")
            qty = data.get("quantita")
            note = data.get("note", "")
            conn.execute(
                "INSERT INTO lista_acquisti (componente_id, quantita, note, stato) VALUES (?, ?, ?, 'Da Acquistare')",
                (comp_id, qty, note))
            conn.commit()
            conn.close()
            return jsonify({"message": "Aggiunto alla lista acquisti"})

        rows = conn.execute("""
            SELECT a.id, a.quantita, a.note, a.stato, c.nome as componente 
            FROM lista_acquisti a 
            JOIN componenti c ON a.componente_id = c.id
            WHERE a.stato = 'Da Acquistare'
        """).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify([]), 200


@app.route("/acquisti/<int:aid>/completa", methods=["PUT"])
@admin_o_tecnico
def completa_acquisto(aid):
    conn = db.get_connection()
    conn.execute("UPDATE lista_acquisti SET stato = 'Acquistato' WHERE id = ?", (aid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Acquisto segnato come completato"})


if __name__ == "__main__":
    app.run(debug=True)
