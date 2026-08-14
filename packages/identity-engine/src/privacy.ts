import type { IdentityPrivacyPolicy, IdentityReferenceSet } from "./types";

export const DEFAULT_IDENTITY_PRIVACY_POLICY: IdentityPrivacyPolicy = Object.freeze({
  allow_face_processing: false,
  allow_persistent_face_index: false,
  cross_tenant_face_index: false,
});

export function assertReferencePrivacy(
  referenceSet: IdentityReferenceSet,
  policy: IdentityPrivacyPolicy = DEFAULT_IDENTITY_PRIVACY_POLICY,
): void {
  if (referenceSet.type !== "FACE") return;
  if (!policy.allow_face_processing) throw new Error("FACE_PROCESSING_NOT_ALLOWED");
  if (policy.allow_persistent_face_index || policy.cross_tenant_face_index) {
    throw new Error("FACE_INDEX_POLICY_INVALID");
  }
  const facePolicy = referenceSet.face_policy;
  if (!facePolicy?.explicit_processing_consent) throw new Error("FACE_EXPLICIT_CONSENT_REQUIRED");
  if (!facePolicy.purpose.trim()) throw new Error("FACE_PROCESSING_PURPOSE_REQUIRED");
  if (facePolicy.persistent_biometric_index !== false) throw new Error("PERSISTENT_FACE_INDEX_FORBIDDEN");
  const retention = Date.parse(facePolicy.retention_until);
  if (!Number.isFinite(retention)) throw new Error("FACE_RETENTION_INVALID");
}
