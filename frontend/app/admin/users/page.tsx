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


export default function UsersPage() {
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
        <h2>Users and invitations</h2>
      </header>

      <article className="card">
        <h3 className="section-title">Invite account</h3>
        <form className="form-grid admin-invite-form" onSubmit={invite}>
          <input
            className="field"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="person@example.org"
            aria-label="Email"
          />
          <select
            className="field"
            value={role}
            onChange={(event) => setRole(event.target.value as UserSummary["role"])}
            aria-label="Role"
          >
            <option value="viewer">Viewer</option>
            <option value="researcher">Researcher</option>
            <option value="admin">Admin</option>
          </select>
          <select
            className="field"
            value={accountType}
            onChange={(event) =>
              setAccountType(event.target.value as UserSummary["account_type"])
            }
            aria-label="Account type"
          >
            <option value="research">Research</option>
            <option value="commercial">Commercial</option>
            <option value="internal">Internal</option>
          </select>
          <button className="button" type="submit">
            <UserPlus size={16} aria-hidden="true" />
            Invite
          </button>
        </form>
        {error ? <p className="error-text">{error}</p> : null}
      </article>

      <article className="card">
        <div className="section-toolbar">
          <h3 className="section-title">Active accounts</h3>
          <button
            className="button secondary-button"
            type="button"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Account type</th>
                <th>Status</th>
                <th>Last login</th>
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
                      <option value="viewer">Viewer</option>
                      <option value="researcher">Researcher</option>
                      <option value="admin">Admin</option>
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
                      <option value="research">Research</option>
                      <option value="commercial">Commercial</option>
                      <option value="internal">Internal</option>
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
                      <option value="active">Active</option>
                      <option value="suspended">Suspended</option>
                    </select>
                  </td>
                  <td>{user.last_login_at || "Never"}</td>
                </tr>
              ))}
              {!loading && users.length === 0 ? (
                <tr><td colSpan={5}>No accounts.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>

      <article className="card">
        <h3 className="section-title">Invitations</h3>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Account type</th>
                <th>Status</th>
                <th>Expires</th>
                <th>Actions</th>
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
                <tr><td colSpan={6}>No invitations.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
