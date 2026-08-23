"use client";

import { FormEvent, useEffect, useState } from "react";
import { Ban, RefreshCw, UserPlus } from "lucide-react";

import {
  createInvitation,
  getInvitations,
  getUsers,
  revokeInvitation,
  updateUser,
} from "@/lib/api";
import type { UserInvitation, UserSummary } from "@/types";
import { useAppPreferences } from "@/lib/preferences";


export default function UsersPage() {
  const { ui } = useAppPreferences();
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [invitations, setInvitations] = useState<UserInvitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserSummary["role"]>("viewer");
  const [accountType, setAccountType] =
    useState<UserSummary["account_type"]>("research");
  const [loading, setLoading] = useState(true);
  const [revokingInvitationId, setRevokingInvitationId] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [nextUsers, nextInvitations] = await Promise.all([
        getUsers(),
        getInvitations(),
      ]);
      setUsers(nextUsers);
      setInvitations(nextInvitations);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      await createInvitation({
        email,
        role,
        account_type: accountType,
      });
      setEmail("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invitation failed");
    }
  }

  async function changeUser(
    userId: string,
    changes: Partial<Pick<UserSummary, "role" | "account_type" | "status">>,
  ) {
    setError("");
    try {
      const updated = await updateUser(userId, changes);
      setUsers((current) =>
        current.map((user) => (user.id === updated.id ? updated : user)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
      await load();
    }
  }

  async function revoke(invitationId: string) {
    setError("");
    setRevokingInvitationId(invitationId);
    try {
      const updated = await revokeInvitation(invitationId);
      setInvitations((current) =>
        current.map((invitation) =>
          invitation.id === updated.id ? updated : invitation,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revocation failed");
      await load();
    } finally {
      setRevokingInvitationId("");
    }
  }

  return (
    <section>
      <header className="page-header">
        <h2>{ui("Users and invitations")}</h2>
      </header>

      <article className="card">
        <h3 className="section-title">{ui("Invite account")}</h3>
        <form className="form-grid admin-invite-form" onSubmit={invite}>
          <input
            className="field"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="person@example.org"
            aria-label={ui("Email")}
          />
          <select
            className="field"
            value={role}
            onChange={(event) => setRole(event.target.value as UserSummary["role"])}
            aria-label={ui("Role")}
          >
            <option value="viewer">{ui("Viewer")}</option>
            <option value="researcher">{ui("Researcher")}</option>
            <option value="admin">{ui("Admin")}</option>
          </select>
          <select
            className="field"
            value={accountType}
            onChange={(event) =>
              setAccountType(event.target.value as UserSummary["account_type"])
            }
            aria-label={ui("Account type")}
          >
            <option value="research">{ui("Research")}</option>
            <option value="commercial">{ui("Commercial")}</option>
            <option value="internal">{ui("Internal")}</option>
          </select>
          <button className="button" type="submit">
            <UserPlus size={16} aria-hidden="true" />
            {ui("Invite")}
          </button>
        </form>
        {error ? <p className="error-text">{error}</p> : null}
      </article>

      <article className="card">
        <div className="section-toolbar">
          <h3 className="section-title">{ui("Active accounts")}</h3>
          <button
            className="button secondary-button"
            type="button"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw size={15} aria-hidden="true" />
            {ui("Refresh")}
          </button>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{ui("User")}</th>
                <th>{ui("Role")}</th>
                <th>{ui("Account type")}</th>
                <th>{ui("Status")}</th>
                <th>{ui("Last login")}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.display_name || user.email}</strong>
                    {user.display_name ? <small>{user.email}</small> : null}
                  </td>
                  <td>
                    <select
                      className="field compact-field"
                      value={user.role}
                      onChange={(event) =>
                        void changeUser(user.id, {
                          role: event.target.value as UserSummary["role"],
                        })
                      }
                    >
                      <option value="viewer">{ui("Viewer")}</option>
                      <option value="researcher">{ui("Researcher")}</option>
                      <option value="admin">{ui("Admin")}</option>
                    </select>
                  </td>
                  <td>
                    <select
                      className="field compact-field"
                      value={user.account_type}
                      onChange={(event) =>
                        void changeUser(user.id, {
                          account_type:
                            event.target.value as UserSummary["account_type"],
                        })
                      }
                    >
                      <option value="research">{ui("Research")}</option>
                      <option value="commercial">{ui("Commercial")}</option>
                      <option value="internal">{ui("Internal")}</option>
                    </select>
                  </td>
                  <td>
                    <select
                      className="field compact-field"
                      value={user.status}
                      onChange={(event) =>
                        void changeUser(user.id, {
                          status: event.target.value as UserSummary["status"],
                        })
                      }
                    >
                      <option value="active">{ui("Active")}</option>
                      <option value="suspended">{ui("Suspended")}</option>
                    </select>
                  </td>
                  <td>{user.last_login_at || "Never"}</td>
                </tr>
              ))}
              {!loading && users.length === 0 ? (
                <tr><td colSpan={5}>{ui("No accounts.")}</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>

      <article className="card">
        <h3 className="section-title">{ui("Invitations")}</h3>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{ui("Email")}</th>
                <th>{ui("Role")}</th>
                <th>{ui("Account type")}</th>
                <th>{ui("Status")}</th>
                <th>{ui("Expires")}</th>
                <th>{ui("Actions")}</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((invitation) => (
                <tr key={invitation.id}>
                  <td>{invitation.email}</td>
                  <td>{invitation.role}</td>
                  <td>{invitation.account_type}</td>
                  <td>{invitation.status}</td>
                  <td>{invitation.expires_at}</td>
                  <td>
                    {invitation.status === "pending" ? (
                      <button
                        aria-label={`Revoke invitation for ${invitation.email}`}
                        className="button secondary-button"
                        disabled={revokingInvitationId === invitation.id}
                        onClick={() => void revoke(invitation.id)}
                        type="button"
                      >
                        <Ban size={15} aria-hidden="true" />
                        {revokingInvitationId === invitation.id
                          ? "Revoking"
                          : "Revoke"}
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
              {!loading && invitations.length === 0 ? (
                <tr><td colSpan={6}>{ui("No invitations.")}</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
